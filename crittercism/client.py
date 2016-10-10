import base64
from datetime import datetime
from datetime import timedelta
import os
import requests


from models import (CRCrash, TimeoutException, MalformedRequestException, AuthenticationException,
                    RateLimitExceededException, ServerErrorException, CrittercismException, PerformanceManagementPie,
                    App, ErrorMonitoringPie, ErrorMonitoringGraph, CRException)


class CrittercismClient(object):
    CRITTERCISM_API_DOMAIN = os.environ.get('CR_API_DOMAIN', 'developers.crittercism.com')
    CRITTERCISM_URL = 'https://%s/v1.0/%s'
    CRITTERCISM_TX_URL = 'https://%s/v1.0/transactions/%s/%s'

    # /allyourbase
    # /v1.0/base
    # /apps/crash/counts
    # /apps/crash/summaries
    # /apps/exception/counts
    # /apps/exception/summaries
    # /errorMonitoring/sparklines
    # /crash/{hash}
    # /crash/{hash}
    # /exception/{hash}
    def __init__(self, auth_hash):
        self._client_id = auth_hash.get('client_id')
        self._username = auth_hash.get('username')
        self._password = auth_hash.get('password')
        self._oauth_token = auth_hash.get('token')
        self._transaction_tokens = {}

        if not self._oauth_token:
            self._oauth_token = self.authenticate()

    def __token_for_app_id(self, app_id):
        token = self._transaction_tokens.get(app_id)
        if not token:
            token = self.authenticate(scope='app/%s/transactions' % app_id)
            self._transaction_tokens[app_id] = token

        return token

    def __request(self, verb, url_suffix, body_data):
        return self.__request_helper(
            verb,
            self.CRITTERCISM_URL % (
                self.CRITTERCISM_API_DOMAIN,
                url_suffix),
            body_data,
            self._oauth_token
        )

    def get_paged_transaction_data(self, app_id, url):
        token = self.__token_for_app_id(app_id)
        pages = []
        page_num = 1
        page = self.__request_helper('GET', url, {}, token)

        while page:
            pages.append(page)
            page_num += 1
            next_url = url + '?pageNum={}'.format(page_num)

            if page.get(u'pagination') and page.get(u'pagination')[u'nextPage']:
                page = self.__request_helper('GET', next_url, {}, token)
            else:
                page = None

        return pages

    def __get_transaction_url(self, url, token):
        return self.__request_helper('GET', url, {}, token)

    def __request_helper(self, verb, url, body_data, token, extra_headers=None):
        headers = {
            'Accept-Encoding': 'gzip, deflate, sdch',
            'Accept-Language': 'en-US,en;q=0.8',
            'Accept': 'application/json',
            'Connection': 'keep-alive',
            'CR-source': 'integration_new_relic'
        }

        if token:
            headers.update({'Authorization': 'Bearer %s' % token})

        if extra_headers:
            headers.update(extra_headers)

        response = None

        if verb == 'GET':
            response = requests.get(url, headers=headers)
        elif verb == 'POST':
            response = requests.post(url, headers=headers, json=body_data)
        elif verb == 'TOKEN':
            response = requests.post(url, headers=headers, params=body_data)
        else:
            raise TypeError

        if not response:
            raise TimeoutException

        # TODO (SF) requests has its own exceptions for these; use them.
        http_response_status = response.status_code
        if http_response_status == 400:
            # 400	Request parameters were invalid/malformed
            raise MalformedRequestException(
                {'message': 'You provided invalid/malformed request parameters.',
                 'response': response})

        elif http_response_status == 401:
            # 401	Invalid oauth token
            raise AuthenticationException(
                {'message': 'You provided an invalid token. Please re-authenticate.',
                 'response': response})

        elif http_response_status == 429:
            # 429	API rate limit exceeded
            raise RateLimitExceededException(
                {'message': 'You have exceeded your rate limit. Please decrease your request frequency.',
                 'response': response})

        elif http_response_status == 500:
            raise ServerErrorException(
                {'message': 'Server error on Crittercism API. Please contact Crittercism support',
                 'response': response})

        elif http_response_status != 200:
            raise CrittercismException(
                {'message': 'Unknown error on Crittercism API.',
                 'response': response})

        return response.json()

    def authenticate(self, scope=None):
        body = {
            'grant_type': 'password',
            'username': self._username,
            'password': self._password,
            'duration': 31536000,
        }

        if scope:
            body['scope'] = scope

        authstr = base64.encodestring('%s' % self._client_id).replace('\n', '')
        data = self.__request_helper('TOKEN', 'https://developers.crittercism.com/v1.0/token', body, None, {
            'Authorization': "Basic %s" % authstr,
            "Content-Type": "application/x-www-form-urlencoded",
        })

        return data['access_token']

    APP_ATTRIBUTE_CHOICES = {"appName",
                             "appType",
                             "appVersions",
                             "crashPercent",
                             "dau",
                             "latency",
                             "latestAppStoreReleaseDate",
                             "latestVersionString",
                             "linkToAppStore",
                             "iconURL",
                             "mau",
                             "rating",
                             "role"}

    # /apps
    def apps(self, attributes=None):
        """The apps endpoint provides information about a customer's mobile applications.
        The apps endpoint returns a list of apps with links to additional metric endpoints.
        Information requested in the attributes parameter is made available as a series of
        key-value pairs inside the object representing each app.

        Required keyword arguments:
        <None>

        Optional keyword arguments:
        attributes -- list of attributes desired as part of app response data
            Possible contents: "appName",
                                "appType",
                                "appVersions",
                                "crashPercent",
                                "dau",
                                "latency",
                                "latestAppStoreReleaseDate",
                                "latestVersionString",
                                "linkToAppStore",
                                "iconURL",
                                "mau",
                                "rating",
                                "role"

        """
        url_suffix = 'apps?attributes=%s' % '%2C'.join(attributes or list(self.APP_ATTRIBUTE_CHOICES))
        content = self.__request('GET', url_suffix, {})

        response = [App(app_id, app_data) for app_id, app_data in content.items()]
        return response

    def app_versions(self, app_id):
        """
        Calls the apps summary endpoint and gets a list of app versions
        for a particular app ID

        :param app_id: string

        :return: list of app version strings
        """
        url_suffix = 'apps?attributes=appVersions'
        content = self.__request('GET', url_suffix, {})

        versions = content[app_id]['appVersions']

        return versions


    # /errorMonitoring/graph
    def error_monitoring_graph(self, error_monitoring_request):
        url_suffix = 'errorMonitoring/graph'
        content = self.__request('POST', url_suffix, {
            'params': error_monitoring_request.as_hash()
        })

        return ErrorMonitoringGraph(content)

    # /errorMonitoring/pie
    def error_monitoring_pie(self, error_monitoring_request):
        url_suffix = 'errorMonitoring/pie'
        content = self.__request('POST', url_suffix, {
            'params': error_monitoring_request.as_hash()
        })

        return ErrorMonitoringPie(content)

    # This helps us override code for unit testing
    def lookback_start(self, t_delta):
        return (datetime.utcnow() - t_delta).strftime('%Y-%m-%dT%H:%M:%S+00:00')

    # /app/{appId}/crash/counts
    # /app/{appId}/crash/summaries
    # /app/{appId}/exception/counts
    # /app/{appId}/exception/summaries
    def app_crash_counts(self, app_id):
        url_suffix = 'app/%s/crash/counts' % app_id
        content = self.__request('GET', url_suffix, {})

        return content

    def crash_paginated_tables(self, app_id, app_version=None,
                               lookback_timedelta=None):
        url_suffix = '{}/crash/paginatedtable'.format(app_id)

        if app_version:
            url_suffix += u'?appVersion={}&'.format(app_version)

        if lookback_timedelta:
            start_date = (datetime.now() - lookback_timedelta).isoformat()
            end_date = datetime.now().isoformat()

            url_suffix += 'startDate={}&endDate={}'.format(start_date,
                                                            end_date)

        content = self.__request('GET', url_suffix, {})

        return content

    def app_crash_summaries(self, app_id, lookback_timedelta=None):
        url_suffix = 'app/%s/crash/summaries' % app_id

        if lookback_timedelta:
            url_suffix += '?lastOccurredStart=%s' % self.lookback_start(lookback_timedelta)

        content = self.__request('GET', url_suffix, {})

        return content

    def crash_details(self, content):
        return CRCrash(content)

    def app_exception_counts(self, app_id):
        url_suffix = 'app/%s/exception/counts' % app_id
        content = self.__request('GET', url_suffix, {})

        return content

    def app_exception_summaries(self, app_id, lookback_timedelta=None):
        url_suffix = 'app/%s/exception/summaries' % app_id

        if lookback_timedelta:
            url_suffix += '?lastOccurredStart=%s' % self.lookback_start(lookback_timedelta)

        content = self.__request('GET', url_suffix, {})

        return content

    def exception_details(self, crash_hash, include_diagnostics=False):
        url_suffix = 'exception/%s?diagnostics=%s&dailyOccurrences=true' % (
                crash_hash, include_diagnostics)
        content = self.__request('GET', url_suffix, {})
        return CRException(content)

    # /performanceManagement/pie
    def performance_management_pie(self, performance_management_request):
        url_suffix = 'performanceManagement/pie'
        content = self.__request('POST', url_suffix, {
            'params': performance_management_request.as_hash()
        })

        return PerformanceManagementPie(content)

    # Transactions Beta Stuff
    def transactions_details(self, app_id, period=None):
        url_suffix = 'details/change/%s' % period
        url = self.CRITTERCISM_TX_URL % (self.CRITTERCISM_API_DOMAIN, app_id, url_suffix)
        content = self.get_paged_transaction_data(app_id, url)
        return content
