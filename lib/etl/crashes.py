from datetime import timedelta
from lib.etl.errors_by_version import ErrorsByVersionProcessor


class CrashETL(ErrorsByVersionProcessor):
    EVENT_TYPE = 'apteligent_crash'

    def __init__(self, app_id, lookback_minutes, new_relic_account, new_relic_app_id):
        super(CrashETL, self).__init__(app_id, lookback_minutes, new_relic_account, new_relic_app_id, self.EVENT_TYPE)

    def get_errors_with_details(self, lookback_minutes):
        """
        Call the the paginatedTables endpoint for 'all' versions of an app
        Get a list of versions from the /apps endpoint for that app
        Call the paginatedTables endpoint for each version
        Build a dict of {hash: {version: daily occurrences}} for each version
        Then for each error hash in the 'all' versions dict, add a new key
        'daily_occurrences_by_version' that has the value of the
        the crashes by version dict to that error hash.

        :param lookback_minutes: int, number of minutes to look back
        :return: list, a list of CRCrash objects
        """
        DAILY_OCCURRENCES = 'daily_occurrences'
        DATA = 'data'
        ERRORS = 'errors'
        HASH = 'hash'

        crash_summaries = self._c_client.crash_paginated_tables(
            self._app_id,
            app_version='all',
            lookback_timedelta=timedelta(minutes=lookback_minutes)
        )

        versions = self._c_client.app_versions(self._app_id)

        daily_occurrences = {}
        for version in versions:
            versioned_summary = self._c_client.crash_paginated_tables(
                self._app_id,
                app_version=version,
                lookback_timedelta=timedelta(minutes=lookback_minutes)
            )
            for error in versioned_summary[DATA][ERRORS]:
                if daily_occurrences.get(error[HASH]):
                    daily_occurrences[error[HASH]][version] = error[DAILY_OCCURRENCES]

                else:
                    daily_occurrences[error[HASH]] = {version: error[DAILY_OCCURRENCES]}
        crashes = []
        for summary in crash_summaries[DATA][ERRORS]:
            summary['daily_occurrences_by_version'] = daily_occurrences.get(
                summary[HASH]
            )
            crashes.append(self._c_client.crash_details(summary))

        return crashes
