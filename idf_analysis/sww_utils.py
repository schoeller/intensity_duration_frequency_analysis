__author__ = "David Camhy, Markus Pichler"
__credits__ = ["David Camhy", "Markus Pichler"]
__license__ = "MIT"
__maintainer__ = "Markus Pichler"

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

from .definitions import COL


class IdfError(Exception):
    """Some Error Within this Package"""


########################################################################################################################
def guess_freq(date_time_index, default=pd.Timedelta(minutes=1)):
    """
    guess the frequency by evaluating the most often frequency

    Args:
        date_time_index (pandas.DatetimeIndex): index of a time-series
        default (pandas.Timedelta):

    Returns:
        pandas.DateOffset: frequency of the date-time-index
    """
    freq = date_time_index.freq
    if pd.notnull(freq):
        return to_offset(freq)

    if not len(date_time_index) <= 3:
        freq = pd.infer_freq(date_time_index)  # 'T'

        if pd.notnull(freq):
            return to_offset(freq)

        delta_series = date_time_index.to_series().diff(periods=1).bfill()  # .fillna(method='backfill')
        counts = delta_series.value_counts()
        counts.drop(pd.Timedelta(minutes=0), errors='ignore')

        if counts.empty:
            delta = default
        else:
            delta = counts.index[0]
            if delta == pd.Timedelta(minutes=0):
                delta = default
    else:
        delta = default

    return to_offset(delta)


########################################################################################################################
def year_delta(years):
    return pd.Timedelta(days=365.25 * years)


########################################################################################################################
def rain_events(series, ignore_rain_below=0.01, min_gap=pd.Timedelta(hours=4)):
    """
    get rain events as a table with start and end times

    Args:
        series (pandas.Series): rain series
        ignore_rain_below (float): where it is considered as rain
        min_gap (pandas.Timedelta): 4 hours of no rain between events

    Returns:
        pandas.DataFrame: table of the rain events
    """
    # best OKOSTRA adjustment with 0.0
    # by ignoring 0.1 mm the results are getting bigger

    # remove values below a from the database
    temp = series[series >= ignore_rain_below].index.to_series()

    if temp.empty:
        return pd.DataFrame()

    # 4 hours of no rain between events
    bool_end = temp.diff(periods=-1) < -min_gap
    bool_end.iloc[-1] = True

    bool_start = temp.diff() > min_gap
    bool_start.iloc[0] = True

    events = pd.DataFrame.from_dict({
        COL.START: temp[bool_start].to_list(),
        COL.END: temp[bool_end].to_list(),
    })
    return events


def event_number_to_series(events, index):
    """
    make a time-series where the value of the event number is paste to the <index>

    Args:
        events (pandas.DataFrame):
        index (pandas.DatetimeIndex):

    Returns:
        pandas.Series:
    """
    ts = pd.Series(index=index)

    events_dict = events.to_dict(orient='index')
    for event_no, event in events_dict.items():
        ts[event[COL.START]: event[COL.END]] = event_no

    return ts


########################################################################################################################
def agg_events(events, series, agg='sum'):
    """

    Args:
        events (pandas.DataFrame): table of events
        series (pandas.Series): time-series data
        agg (str | function): aggregation of time-series

    Returns:
        numpy.ndarray: result of function of every event
    """
    if events.empty:
        return np.array([])

    if events.index.size > 3500:
        res = series.groupby(event_number_to_series(events, series.index)).agg(agg).values
    else:
        # res = []
        # for _, event in events.iterrows():
        #     res.append(series[event[COL.START]:event[COL.END]].agg(agg))
        res = events.apply(lambda event: series[event[COL.START]:event[COL.END]].agg(agg), axis=1).values
    return res


########################################################################################################################
def event_duration(events):
    """
    calculate the event duration

    Args:
        events (pandas.DataFrame): table of events with COL.START and COL.END times

    Returns:
        pandas.Series: duration of each event
    """
    return events[COL.END] - events[COL.START]


########################################################################################################################
def rain_bar_plot(rain, ax=None, color='#1E88E5', reverse=False, step='post', joinstyle='miter', capstyle='butt'):
    """
    Make a standard precipitation/rain plot.

    Args:
        rain (pandas.Series):
        ax (matplotlib.axes.Axes):
        color (str):
        reverse (bool):
        step (str):  'mid' 'post' pre'

    Returns:
        matplotlib.axes.Axes: rain plot
    """
    if rain.size == 1:
        freq_step = pd.Timedelta(rain.index.freq)
        rain = rain.reindex(pd.date_range(rain.index[0]-freq_step, periods=3, freq=rain.index.freq))
    ax = rain.plot(ax=ax, drawstyle=f'steps-{step}', color=color, solid_capstyle=capstyle, solid_joinstyle=joinstyle,
                   lw=0)
    ax.fill_between(rain.index, rain.values, 0, step=step, zorder=1000, color=color, capstyle=capstyle,
                    joinstyle=joinstyle)

    if reverse:
        # ax.set_ylim(top=0, bottom=rain.max() * 1.1)
        ax.set_ylim(bottom=0)
        ax.invert_yaxis()
    else:
        ax.set_ylim(bottom=0)

    return ax


########################################################################################################################
def resample_rain_series(series):
    """
    Resamples a rain time-series to an appropriate frequency based on the duration of the series.

    The function determines the optimal resampling frequency (in minutes) by comparing the total duration
    of the series against predefined thresholds. If the original frequency is already finer than the
    calculated optimal frequency, the series is returned unchanged. Otherwise, the series is resampled
    to the new frequency by summing the values within each interval.

    Args:
        series (pandas.Series): A time-series of rain data, indexed by a pandas.DatetimeIndex.
                                The series should contain numeric values representing rain amounts.

    Returns:
        tuple[pandas.Series, int]: A tuple containing:
            - The resampled time-series (if resampling was applied) or the original series (if no resampling was needed).
            - The final frequency of the series in minutes (e.g., 5 for 5-minute intervals).

    Notes:
        - The resampling thresholds are defined as follows:
            - Duration < 5 hours: 1-minute frequency.
            - Duration < 12 hours: 2-minute frequency.
            - Duration < 1 day: 5-minute frequency.
            - Duration < 2 days: 10-minute frequency.
            - Duration < 3 days: 15-minute frequency.
            - Duration < 4 days: 20-minute frequency.
        - If the original frequency of the series is finer than the calculated optimal frequency,
          the series is returned unchanged, and the original frequency is converted to minutes.
        - Resampling is performed using the sum of values within each interval to preserve the total rain amount.
    """
    resample_minutes = (
        (pd.Timedelta(hours=5), 1),
        (pd.Timedelta(hours=12), 2),
        (pd.Timedelta(days=1), 5),
        (pd.Timedelta(days=2), 10),
        (pd.Timedelta(days=3), 15),
        (pd.Timedelta(days=4), 20)
    )

    dur = series.index[-1] - series.index[0]
    freq = guess_freq(series.index)

    minutes = 1
    for duration_limit, minutes in resample_minutes:
        if dur < duration_limit:
            break

    if pd.Timedelta(freq) > pd.Timedelta(minutes=minutes):
        return series, int(freq / pd.Timedelta(minutes=1))

    # print('resample_rain_series: ', dur, duration_limit, minutes)
    return series.resample(f'{minutes}min').sum(), minutes
