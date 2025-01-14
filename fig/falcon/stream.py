import sys
import datetime
import time
import threading
import requests

from .api import FalconAPI
from .models import Event, Stream
from ..util import StoppableThread
from ..log import log
from ..config import config


class StreamManagementThread(threading.Thread):
    """Thread that spins-out sub-threads to manage CrowdStrike Falcon Streaming API"""

    def __init__(self, output_queue, *args, **kwargs):
        kwargs['name'] = kwargs.get('name', 'cs_mngmt')
        super().__init__(*args, **kwargs)
        self.output_queue = output_queue

    def run(self):
        while True:
            try:
                workers_died_event = self.start_workers()
                while not workers_died_event.is_set():
                    time.sleep(60)
                log.debug("Restarting stream session")
            except Exception:  # pylint: disable=W0703
                log.exception("Could not restart stream session")
                sys.exit(1)  # TODO implement re-try mechanism

    def start_workers(self):
        stop_event = threading.Event()
        falcon_api = FalconAPI()
        application_id = config.get('falcon', 'application_id')
        for stream in falcon_api.streams(application_id):
            StreamingThread(stream, self.output_queue, stop_event=stop_event).start()
            StreamRefreshThread(application_id, stream, falcon_api, stop_event=stop_event).start()
        return stop_event


class StreamRefreshThread(StoppableThread):
    def __init__(self, application_id, stream: Stream, falcon_api: FalconAPI, *args, **kwargs):
        kwargs['name'] = kwargs.get('name', 'cs_refresh')
        super().__init__(*args, **kwargs)
        self.stream = stream
        self.falcon_api = falcon_api
        self.application_id = application_id

    def run(self):
        try:
            self.sleep()
            while not self.stopped:
                self.refresh_stream_session()
                self.sleep()

        finally:
            self.stop()

    def sleep(self):
        time.sleep(self.stream.refresh_interval * 9 / 10)

    def refresh_stream_session(self):
        self.falcon_api.refresh_streaming_session(self.application_id, self.stream)
        log.debug("Refresh of streaming session succeeded")


class StreamingThread(StoppableThread):
    def __init__(self, stream: Stream, queue, *args, **kwargs):
        kwargs['name'] = kwargs.get('name', 'cs_stream')
        super().__init__(*args, **kwargs)
        self.conn = StreamingConnection(stream, queue.last_offset())
        self.queue = queue

    def run(self):
        try:
            for event in self.conn.events():
                if event:
                    self.process_event(event)

                if self.stopped:
                    break
        except requests.exceptions.ChunkedEncodingError:
            pass  # ChunkedEncodingError is expected when streaming session closes abruptly
        finally:
            log.warning("Streaming Connection was closed.")
            if not self.stopped:
                self.stop()
            else:
                self.conn.close()

    def process_event(self, event):
        event = Event(event)
        if not event.irrelevant():
            self.queue.put(event)


class StreamingConnection():
    def __init__(self, stream: Stream, last_seen_offset=0):
        self.stream = stream
        self.connection = None
        self.last_seen_offset = last_seen_offset

    def open(self):
        headers = {
            'Authorization': 'Token %s' % (self.stream.token),
            'Date': datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000'),
            'Connection': 'Keep-Alive'
        }
        log.info("Opening Streaming Connection")
        url = self.stream.url + '&offset={}'.format(self.last_seen_offset)
        self.connection = requests.get(url, headers=headers, stream=True)
        return self.connection

    def events(self):
        return self.open().iter_lines()

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
