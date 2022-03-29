import numpy as np
import pandas as pd
from math import floor
from abc import ABC, abstractmethod


class _AbstractModelRain(ABC):
    def __init__(self, idf=None):
        """

        Args:
            idf (idf_analysis.IntensityDurationFrequencyAnalyse):
        """
        self.idf = idf

    def _get_index(self, duration, interval=5):
        return range(interval, duration + interval, interval)

    def _get_idf_value(self, duration, return_period):
        return self.idf.depth_of_rainfall(duration, return_period)

    @abstractmethod
    def get_series(self, return_period, duration, interval=5, **kwargs):
        pass

    def get_time_series(self, return_period, duration, interval=5, start_time=None, **kwargs):
        rain = self.get_series(return_period, duration, interval, **kwargs)
        if start_time is not None:
            if isinstance(start_time, str):
                start_time = pd.to_datetime(start_time)
            rain.index = start_time + pd.to_timedelta(rain.index, unit='m')
            rain = rain.asfreq(pd.infer_freq(rain.index))
        return rain


class _BlockRain(_AbstractModelRain):
    def __init__(self, idf=None):
        _AbstractModelRain.__init__(self, idf)

    def get_series(self, return_period, duration, interval=5, **kwargs):
        index = self._get_index(duration, interval)
        height = self._get_idf_value(duration, return_period)
        intensity = height / len(index)
        r = pd.Series(index=index, data=intensity)
        r = r.append(pd.Series({0: 0})).sort_index()
        return r


class _EulerRain(_AbstractModelRain):
    def __init__(self, idf=None):
        _AbstractModelRain.__init__(self, idf)

    @staticmethod
    def _get_occurrence_highest_intensity(kind=2):
        if kind == 1:
            return 0
        elif kind == 2:
            return 1 / 3

    def get_series(self, return_period, duration, interval=5, kind=2):
        index = self._get_index(duration, interval)
        height = pd.Series(data=self._get_idf_value(np.array(index), return_period), index=index)

        height_diff = height.diff()
        height_diff.iloc[0] = height.iloc[0]

        max_index = floor(round((self._get_occurrence_highest_intensity(kind) * duration) / interval, 3)) * interval

        # sort differences and reset index
        r = height_diff.sort_values(ascending=False)
        r.index = sorted(r.index.values)

        # reverse first <occurrence_highest_intensity> values
        r.loc[:max_index] = r.loc[max_index::-1].values

        # add Zero value at first posiotion (for SWMM ?)
        r = r.append(pd.Series({0: 0})).sort_index()

        return r