import cookielib
import mimetools
import json
import urllib2
import os
from urlparse import urljoin


class APIError(Exception):
        pass


# We override urllib2.Request so we can actually do a PUT request
class PutRequest(urllib2.Request):

    def __init__(self, url, body='', headers={}):
        urllib2.Request.__init__(self, url, body, headers)
        self.method = 'PUT'

    def get_method(self):
        return self.method


# This once was shamelessly ripped off from post-review
# It has now gained support for the new api, but without
# copy-ing everything from post-review, because we simply
# don't need all that.
class ReviewBoardServer(object):
    """An instance of a Review Board server."""
    def __init__(self, url, username, password):
        rb_username = username
        rb_password = password
        self.root_resource = None
        self.url = url
        if self.url[-1] != '/':
            self.url += '/'

        passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password("Web API", self.url,
                             rb_username, rb_password)

        authhandler = urllib2.HTTPBasicAuthHandler(passman)
        opener = urllib2.build_opener(authhandler)

        cj = cookielib.CookieJar()
        opener.add_handler(urllib2.HTTPCookieProcessor(cj))

        urllib2.install_opener(opener)

        self.root_resource = self.api_get('api/')

    def get_reviews(self, last_from_date, last_to_date):
        """Returns reviews based date last updated"""
        index = 0
        review_list = []
        while True:
            url = self._make_reviews_url(last_from_date, last_to_date, index)
            rsp = self.api_get(url)
            review_list += rsp['review_requests']
            index += 201
            if not 'next' in rsp['links']:
                break

        return review_list

    def get_review(self, review_request_id):
        """Returns the review request with the specified ID."""
        url = '%s%s/' % (\
            self.root_resource['links']['review_requests']['href'], \
                review_request_id)
        rsp = self.api_get(url)
        return rsp['review_request']

    def get_useremail(self, username):
        url = os.path.join(self.root_resource['links']['users']['href'],
                           username)
        rsp = self.api_get(url)
        return rsp['user']['email']

    def set_discarded(self, review_request_id, message):
        """Marks a review request as submitted if it is not already."""
        review_request = self.get_review(review_request_id)
        arguments = {'status': 'discarded'}
        arguments['description'] = message
        self.api_put(review_request['links']['update']['href'], arguments)

    def process_json(self, data):
        """
        Loads in a JSON file and returns the data if successful. On failure,
        APIError is raised.
        """
        rsp = json.loads(data)

        if rsp['stat'] == 'fail':
            raise APIError(rsp)
        return rsp

    def _make_reviews_url(self, last_from_date, last_to_date, index):
        """Given date range and index
           will create the url for review requests
        """

        url = '%s/?last-updated-to=%s&last-updated-from=%s' \
              '&start=%d&max-results=200' % (\
            self.root_resource['links']['review_requests']['href'],
             last_from_date, last_to_date, index)
        return url

    def _make_url(self, path):
        """Given a path on the server returns a full http:// style url"""
        url = urljoin(self.url, path)
        if not url.startswith('http'):
            url = 'http://%s' % url
        return url

    def http_put(self, path, fields, files=None):
        """Performs an HTTP PUT on the specified path."""
        url = self._make_url(path)

        content_type, body = self._encode_multipart_formdata(fields, files)
        headers = {
            'Content-Type': content_type,
            'Content-Length': str(len(body))
        }
        r = PutRequest(url, body, headers)
        data = urllib2.urlopen(r).read()
        return data

    def http_get(self, path):
        """Performs an HTTP GET on the specified path."""
        url = self._make_url(path)
        rsp = urllib2.urlopen(url).read()
        return rsp

    def api_put(self, path, fields=None, files=None):
        """Performs an API call using HTTP PUT at the specified path."""
        return self.process_json(self.http_put(path, fields, files))

    def api_get(self, path):
        """Performs an API call using HTTP GET at the specified path."""
        return self.process_json(self.http_get(path))

    def _encode_multipart_formdata(self, fields, files):
        """
        Encodes data for use in an HTTP POST.
        """
        BOUNDARY = mimetools.choose_boundary()
        content = ""

        fields = fields or {}
        files = files or {}

        for key in fields:
            content += "--" + BOUNDARY + "\r\n"
            content += "Content-Disposition: form-data; name=\"%s\"\r\n" % key
            content += "\r\n"
            content += fields[key] + "\r\n"

        for key in files:
            filename = files[key]['filename']
            value = files[key]['content']
            content += "--" + BOUNDARY + "\r\n"
            content += "Content-Disposition: form-data; name=\"%s\"; " % key
            content += "filename=\"%s\"\r\n" % filename
            content += "\r\n"
            content += value + "\r\n"

        content += "--" + BOUNDARY + "--\r\n"
        content += "\r\n"

        content_type = "multipart/form-data; boundary=%s" % BOUNDARY

        return content_type, content
