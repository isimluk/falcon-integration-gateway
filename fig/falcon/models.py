import json
import re
import datetime
from ..config import config


class Event(dict):
    def __init__(self, event_string):
        event = json.loads(event_string.decode('utf-8'))
        super().__init__(event)

    def irrelevant(self):
        return self['metadata']['eventType'] != 'DetectionSummaryEvent' \
            or self.severity < int(config.get('events', 'severity_threshold')) \
            or self.creation_time < self.cut_off_date()

    @property
    def offset(self):
        return self['metadata']['offset']

    @property
    def severity(self):
        return self['event'].get('Severity', 5)

    @property
    def creation_time(self):
        return self.parse_cs_time(self['metadata']['eventCreationTime'])

    @property
    def sensor_id(self):
        return self['event']['SensorId']

    @classmethod
    def parse_cs_time(cls, cs_timestamp):
        return datetime.datetime.utcfromtimestamp(float(cs_timestamp) / 1000.0)

    @classmethod
    def cut_off_date(cls):
        return datetime.datetime.now() - datetime.timedelta(days=int(config.get('events', 'older_than_days_threshold')))


class Stream(dict):
    @property
    def token(self):
        return self['sessionToken']['token']

    @property
    def url(self):
        return self['dataFeedURL']

    @property
    def refresh_interval(self):
        return self['refreshActiveSessionInterval']

    @property
    def partition(self):
        match = re.match(r'.*\/sensors\/entities\/datafeed-actions/v1/([0-9a-zA-Z]+)\?',
                         self['refreshActiveSessionURL'])
        if not match or not match.group(1):
            raise Exception('Cannot parse stream partition from stream data: {}'.format(self))
        return match.group(1)


class TestEvent(dict):
    """Test event is sent to backends that accept it after the application is properly initialized. This allows customers to visualy see the event has been delivered."""
    @property
    def offset(self):
        return 0

    @property
    def cloud_provider(self):
        return "GCP"

    @property
    def mdm_identifier(self):
        return None

    @property
    def 
