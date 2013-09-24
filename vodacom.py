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
# logging
# implement rumps

# Local
import httplib
import urllib
import json
import pprint
import subprocess
import datetime
import calendar

# Third-party
import rumps

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
    return {'User-Agent': 'myvodacom/3.0.1 CFNetwork/609.1.4 Darwin/13.0.0',
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
    peak_available = sum(data_item['remaininginmetric'] 
                          for data_item in json_data['dataTotalBean'])
    off_peak_available = sum([kb_from_human_readable(data_item['totalBundleRemaining'])
                              for data_item in
                              json_data['getBalancesOutDTO']['dataBalancesOutDTO'] 
                              if data_item['serviceTypeString'].startswith('Night Owl')])
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

def print_info(info):
    """
    Prints info to stdout.
    """
    print('======= Peak =======')
    print('Available: {0}'.format(human_readable(info['peak_available'])))
    print('Per day: {0}'.format(human_readable(info['daily_peak_remaining'])))
    print('Today: {0}'.format(human_readable(info['peak_usage'])))
    print('Usage: {0:.1%}'.format(info['peak_usage_percentage']))
    print('===== Off-Peak =====')
    print('Available: {0}'.format(human_readable(info['off_peak_available'])))
    print('Today: {0}'.format(human_readable(info['off_peak_usage'])))
    print('====================')
                 
if __name__ == "__main__":
	# CONFIG =============================================================================        
	# The username to log in with
	username = '082xxxxxxx'
	# The password for the username above
	password = 'password'
	# The MSISDN for which you require the balance
	msisdn = '082xxxxxxx'
	# The host name providing the REST API
	host = 'www.vodacom.mobi'
	# The resource for logging in
	auth_path = '/coza_rest_5_0/auth'
	# The resource template where we'll get the balance information
	info_path = '/coza_rest_5_0/postlogin/details?msisdn={0}&vodacomauth_token={1}&linkedmsisdn={2}'
	# The script to invoke to get hourly data usage from a monitor
	# In this case, I'm have an internet gateway where data is monitored using vnstat.
	# The data is retrieved over an SSH tunnel using SSH keys. 
	usage_args = ["ssh", "192.168.0.1", "'./Scripts/get_today_hourly_usage.sh'"]
		   
	# COLLECT ============================================================================
	headers = get_headers()
	(headers['Cookie'], auth_token) = log_in(host, auth_path, headers, username, password)
	info_path = info_path.format(username, auth_token, msisdn)
	json_data = get_data(host, info_path, headers)
	hourly_usage = get_hourly_usage(usage_args)

	# OUTPUT =============================================================================
	today = datetime.date.today()
	(peak_usage, off_peak_usage) = split_data_usage(hourly_usage, today)
	(peak_available, off_peak_available) = get_available_data(json_data)
	(daily_peak_remaining, peak_usage_percentage) = calculate_daily_quota_and_usage(today, peak_available, peak_usage)
	info = {'peak_available': peak_available,
			'daily_peak_remaining': daily_peak_remaining,
			'peak_usage': peak_usage,
			'peak_usage_percentage': peak_usage_percentage,
			'off_peak_available': off_peak_available,
			'off_peak_usage': off_peak_usage}
	print_info(info)

