#!/usr/bin/python
# Copyright 2013 Pieter Rautenbach
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#   http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# TODO:
# background updating
# py2app (WIP, can't install)
# auto start (plist, LaunchDaemon, post-install script)
# notifications (50%, 80%, 95%)
# update screen shot

# Local
import argparse
import calendar
import ConfigParser
import datetime
import httplib
import json
import logging.config
import os.path
import pprint
import subprocess
import threading
import urllib

# Third-party
import rumps

# Constants
USER_AGENT = 'myvodacom/333 CFNetwork/672.1.15 Darwin/14.0.0'

def human_readable(kb):
    """
    Returns an input value in KB in the smallest unit with a value larger than one as a 
    human readable string with the chosen unit.
    """
    format = "%3.2f %s"
    for x in ['KiB','MiB','GiB']:
        if kb < 1024.0 and kb > -1024.0:
            return format % (kb, x)
        kb /= 1024.0
    return format % (kb, 'TiB')

def kb_from_human_readable(s):
    """
    Returns the value in KB from a human readable string with a unit.
    """
    unit_multiplier = {'KiB': 1, 
                       'KB':  1, 
                       'MiB': 1024,
                       'MB':  1024, 
                       'GiB': 1024*1024,
                       'GB':  1024*1024,
                       'TiB': 1024*1024*1024,
                       'TB':  1024*1024*1024}
    (value, unit) = s.split()
    return float(value)*unit_multiplier[unit]

def get_headers():
    """
    A standard set of headers we'll use for all requests.
    """
    return {'User-Agent': USER_AGENT,
            'Content-Type': 'application/x-www-form-urlencoded', 
            'Accept': 'application/json',
            'Accept-Language': 'en-gb',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'}

def log_in(host, resource, headers, username, password):
    """
    Log the user in and returns the cookie and auth token as a tuple.
    """
    parameters = urllib.urlencode({'password': password, 'username': username})
    connection = httplib.HTTPSConnection(host)
    connection.request('POST', resource, parameters, headers)
    response = connection.getresponse()
    json_data = json.load(response)
    logger.debug("\n{0}".format(pprint.pformat(json_data)))
    cookie = response.getheader('Set-Cookie')
    auth_token = response.getheader('VodacomAuth-Token')
    connection.close()
    return (cookie, auth_token)

def get_data(host, resource, headers):
    """
    Returns a JSON structure for data retrieved (GET) from the resource.
    """
    connection = httplib.HTTPSConnection(host)
    connection.request('GET', resource, None, headers)
    response = connection.getresponse()
    json_data = json.load(response)
    connection.close()
    return json_data

def get_hourly_usage(script_args):
    """
    Returns hourly usage assuming vnstat output (that's your API). Input is a list of 
    elements making up the command-line invocation of the script.
    """
    process = subprocess.Popen(script_args, stdout=subprocess.PIPE)
    (out, _) = process.communicate()
    return out

def split_data_usage(hourly_usage, today):
    """
    Returns a tuple (peak_usage, off_peak_usage) for the hourly usage input (the output
    from vnstat). Off-peak is considered to be between 00:00 and 05:00.
    """
    lines = hourly_usage.split()
    peak_usage = 0
    off_peak_usage = 0
    for l in lines:
        # See man vnstat for its output's format
        items = l.split(';')
        t = datetime.datetime.fromtimestamp(int(items[2]))
        if today.day == t.day:
            # The sum of rx and tx data for this hour interval
            delta = int(items[3]) + int(items[4])
            if t.hour >= 5:
                peak_usage += delta
            else:
                off_peak_usage += delta
    return (peak_usage, off_peak_usage)
            
def get_available_data(json_data):
    """
    Returns the available data as a tuple (peak_available, off_peak_available).
    """
    peak_available = sum(data_item['remaininginmetric'] for data_item in json_data['dataTotalBean'])
    logger.debug('Peak available: {0}'.format(peak_available))
    balances_detail = json_data['dataBalancesOutDTO']
    # logger.debug(pprint.pformat(balances_detail))
    off_peak_balances = [data_item for data_item in balances_detail if data_item['serviceTypeString'].startswith('Night Owl')]
    # logger.debug(pprint.pformat(off_peak_balances))
    off_peak_available = sum([data_item['remaininginmetric'] for data_item in off_peak_balances[0]['dataBalancesBean']])
    logger.debug('Off-peak available: {0}'.format(off_peak_available))
    return (peak_available, off_peak_available)
            
def calculate_daily_quota_and_usage(today, available_data, current_usage):
    """
    Calculates the amount of data available per day until the end of the month and
    the current usage as a percentage.
    """
    (_, days_in_month) = calendar.monthrange(today.year, today.month)
    end_of_month = datetime.date(today.year, today.month, days_in_month)
    days_remaining = (end_of_month - today).days + 1
    daily_remaining = available_data/float(days_remaining)
    usage = current_usage/daily_remaining
    return (daily_remaining, usage)

def get_console_formatted_info(info):
    """
    Returns a formatted info summary.
    """
    s = ("============ Peak ============\n"
         "Available:      {0:>14}\n"
         "Per day:        {1:>14}\n"
         "Today:          {2:>14}\n"
         "Usage:          {3:>14,.1%}\n"
         "========== Off-Peak ==========\n"
         "Available:      {4:>14}\n"
         "Today:          {5:>14}\n"
         "==============================").format(human_readable(info['peak_available']),
                 human_readable(info['daily_peak_remaining']),
                 human_readable(info['peak_usage']),
                 info['peak_usage_percentage'],
                 human_readable(info['off_peak_available']),
                 human_readable(info['off_peak_usage']))
    return s
                 
def get_simple_formatted_info(info):
    """
    Returns a simple formatted info summary.
    """
    s = ("Peak\n"
         "Available: {0}\n"
         "Per day: {1}\n"
         "Today: {2}\n"
         "Usage:  {3:.1%}\n\n"
         "Off-Peak\n"
         "Available: {4}\n"
         "Today: {5:}\n\n"
         "Last Update: {6}").format(human_readable(info['peak_available']),
                 human_readable(info['daily_peak_remaining']),
                 human_readable(info['peak_usage']),
                 info['peak_usage_percentage'],
                 human_readable(info['off_peak_available']),
                 human_readable(info['off_peak_usage']),
                 info['last_update'].strftime('%x %X'))
    return s
    
def get_audit(info):
    """
    Prints output in a format that can be parsed from a log file.
    Spec: <available_peak>,
          <per_day_peak_remaining>,
          <today_peak_usage>,
          <peak_usage_percentage>,
          <available_off_peak>,
          <today_off_peak_usage>
    """
    return "{0},{1},{2},{3},{4},{5}".format(info['peak_available'],
                                            info['daily_peak_remaining'],
                                            info['peak_usage'],
                                            info['peak_usage_percentage'],
                                            info['off_peak_available'],
                                            info['off_peak_usage'])

def get_logger(conf_path):
    """
    Initialise the logger from a config file.
    """
    logging.config.fileConfig(conf_path)
    logger = logging.getLogger()
    return logger
    
def get_arguments():
    """
    Create and return a command-line argument parser.
    """
    description = "Utility for compiling a data usage summary."
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--headless', help="Don't use the GUI", action='store_true')
    return parser.parse_args()

@rumps.timer(5*60)
def reload_info_callback(sender):
    """
    Timer callback for reloading all info.
    """
    # We don't use any locking, as we assume that the interval between runs will be less
    # than the time to retrieve the data
    #thread = threading.Thread(target=reload_info)
    #thread.daemon = True
    #thread.start()
    reload_info()

@rumps.clicked('Summary')
def summary_callback(_):
    global info
    if len(info) > 1:
        rumps.alert(get_simple_formatted_info(info))
    else:
        msg = "No information available. Please refresh or wait until the next hour elapses."
        rumps.alert(msg)
        logger.warning(msg)
        
@rumps.clicked('Refresh')
def refresh_callback(_):
    global info
    try:
        last_update = info['last_update']
        info['last_update'] = None
        reload_info_callback(None)
    except Exception, e:
        info['last_update'] = last_update
    
def reload_info():
    """
    Reload info and update the status bar.
    """
    global logger, app, info
    old_title = app.title
    app.title = "Updating..."
    try:
        update_info()
        if info.has_key('peak_usage') and info.has_key('peak_usage_percentage'):
            app.title = "{0} ({1:.1%})".format(human_readable(info['peak_usage']),         
                                               info['peak_usage_percentage'])
        else:
            app.title = "No Info"
    except Exception, e:
        logger.exception(e)
        if app.title == "Updating...":
            app.title = "No Info"
        else:
            app.title = old_title
            
def update_info():
    """
    Returns a dictionary of all info.
    """
    global logger, info
    logger.info("Loading configuration")
    default = 'default'
    config_parser = ConfigParser.SafeConfigParser()
    config_file = open('{0}/conf/{1}.conf'.format(os.path.dirname(__file__), os.path.splitext(os.path.basename(__file__))[0]))
    config_parser.readfp(config_file)
    # The username to log in with
    username = config_parser.get(default, 'username')
    # The password for the username above
    password = config_parser.get(default, 'password')
    # The MSISDN for which you require the balance
    msisdn = config_parser.get(default, 'msisdn')
    # The host name providing the REST API
    host = config_parser.get(default, 'host')
    # The monitor for local data usage
    monitor = config_parser.get(default, 'monitor')
    # The resource for logging in
    auth_path = "/coza_rest_10_0/basicauth"
    # The resource template where we'll get the balance information
    info_path = ("/coza_rest_10_0/balances?msisdn={0}&token={1}&linkedmsisdn={2}")
    # The script to invoke to get hourly data usage from a monitor
    # In this case, I'm have an internet gateway where data is monitored using vnstat.
    # The data is retrieved over an SSH tunnel using SSH keys. 
    usage_args = monitor.split()
    logger.debug(("Configuration:"
                  "\n\tUsername: {0}"
                  "\n\tPassword: {1}"
                  "\n\tMSISDN:   {2}"
                  "\n\tHost:     {3}")
                  .format(username, 
                          "**********", 
                          msisdn, 
                          host))

    # Update the last update timestamp to now
    now = datetime.datetime.now()
    last_update = info['last_update'] if info.has_key('last_update') else None
    info['last_update'] = now

    # Get remote info -- every hour, on the hour (or the first chance we get), or if
    # it's the first time we're executing
    if (last_update is None or  # We've never updated
        now.hour != last_update.hour or  # Or we've crossed an hour boundary
        (now - last_update).total_seconds()/(60*60) > 1):  # Or we haven't updated in 1 hour
        headers = get_headers()
        logger.info("Logging in")
        (headers["Cookie"], auth_token) = log_in(host, auth_path, headers, username, password)
        if auth_token is None:
            logger.error("Not logged in -- check config")
            return
        info_path = info_path.format(username, auth_token, msisdn)
        logger.info("Retrieving data balances from {0}".format(host))
        json_data = get_data(host, info_path, headers)
        logger.debug("\n{0}".format(pprint.pformat(json_data)))
        (info['peak_available'], info['off_peak_available']) = get_available_data(json_data)
    else:
        logger.info("Skipping remote retrieval")
    
    # Get local info and build summary
    logger.info("Retrieving data usage")
    hourly_usage = get_hourly_usage(usage_args)
    logger.info("Compiling summary")
    today = datetime.date.today()
    (info['peak_usage'], info['off_peak_usage']) = split_data_usage(hourly_usage, today)
    (info['daily_peak_remaining'], info['peak_usage_percentage']) = calculate_daily_quota_and_usage(today, info['peak_available'], info['peak_usage'])
    logger.info("Audit: {0}".format(get_audit(info)))

def main(headless=False):
    """
    Main method.
    """
    global logger, app, info
    if headless:
        logger.info("Running headless")
        update_info()           
        print(get_console_formatted_info(info))
    else:
        p = os.path.dirname(os.path.abspath(__file__))
        timer = rumps.Timer(reload_info_callback, 5)
        summary = rumps.MenuItem('Summary', 
                                 icon='{0}/icons/summary_24x24.png'.format(p), 
                                 dimensions=(16, 16))
        refresh = rumps.MenuItem('Refresh', 
                                 icon='{0}/icons/refresh_24x24.png'.format(p), 
                                 dimensions=(16, 16))
        app = rumps.App('Vodacom', 
                        icon='{0}/icons/app_24x24.png'.format(p),
                        menu=(summary, refresh, None))
        app.run()

if __name__ == "__main__":
    """
    Main entry point.
    """
    p = os.path.dirname(os.path.abspath(__file__))
    l = "{0}/conf/logger.conf".format(p)
    logger = get_logger(l)
    info = {}
    #from Foundation import NSAutoreleasePool
    #pool = NSAutoreleasePool.alloc().init()
    try:
        args = get_arguments()
        main(headless=args.headless)
    except Exception, e:
        logger.exception(e)
    #del pool