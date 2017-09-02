
import urllib2, urllib, json, traceback
from collections import defaultdict
from datetime import date, datetime
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import auth
from django.core.mail import EmailMessage
from models import Reminder
from forms import AddReminderForm
import urllib, urllib2
import json

def manage(request):
   user_id = None
   if request.user.is_authenticated():
       user_id = request.user.id
   else:
       return HttpResponseRedirect("/accounts/login")

   if request.method == 'POST':
       post_form = AddReminderForm(request.POST)
       if post_form.is_valid():
           zipcode = post_form.cleaned_data['zipcode']
           reminder = post_form.cleaned_data['reminder']
           Reminder.objects.create(user_id=user_id, zipcode=zipcode, warning_event=reminder)

   reminders = Reminder.objects.filter(user_id=user_id)
   form = AddReminderForm()
   return render(request, 'manage.html', {'form': form, 'reminders': reminders, 'logged_in': True})


def del_reminder(request):
   if not request.user.is_authenticated():
       return HttpResponseRedirect("/accounts/login")
   try:
       reminder_id = int(request.GET.get('id', ''))
       p = Reminder.objects.get(id=int(reminder_id))
       p.delete()
   except:
       pass
   return HttpResponseRedirect("/")

def get_weather(zipcode):
    appid = '28930bfb1cc49ac865b66074f0b4bdab'
    baseurl = "https://query.yahooapis.com/v1/public/yql?"
    yql_query = "select * from weather.forecast where woeid in (select woeid from geo.places(1) where text=\"%s\")" % zipcode
    yql_url = baseurl + urllib.urlencode({'q':yql_query}) + "&format=json"
    result = urllib2.urlopen(yql_url).read()
    data = dict()
    try:
        data = json.loads(result)['query']['results']['channel']
    except:
        print(traceback.format_exc())
    return data


def generate_weather_string(data):
 #  return "The weather condition will be %s in %s on %s. The temperature will be %s to %s F." % (
   return "It will be %s in %s on %s. The temperature will be %s to %s %s." % (
       data['item']['forecast'][1]['text'],
       data['location']['city'],
       data['item']['forecast'][1]['date'],
       data['item']['forecast'][1]['low'],
       data['item']['forecast'][1]['high'],
       data['units']['temperature'],
   )


def test_email(request):
  user_id = None
  if request.user.is_authenticated():
      user_id = request.user.id
  else:
      return HttpResponseRedirect("/accounts/login")
  reminders = Reminder.objects.filter(user_id=user_id)
  # De-duplicate zipcode. //the same zipcode has many reminders like raining, snowing, etc
  zipcodes = set()
  for reminder in reminders:
      zipcodes.add(reminder.zipcode)
  body = "Dear %s,\n\n" % request.user.username
  for zipcode in zipcodes:
      body += generate_weather_string(get_weather(zipcode)) + "\n"
  body += "\nBest,\nWeather Reminder"
  message = EmailMessage("Weather Report", body, to=[request.user.email]) #EmailMessage in Django, sending email
  message.send()
  return HttpResponseRedirect("/")


def secret_trigger(request):
  reminders = Reminder.objects.all()
  zip_reminders_map = defaultdict(list)
  # Aggregate by zipcode
  for reminder in reminders:
      zip_reminders_map[reminder.zipcode].append(reminder)
  # Aggregate by user email
  emails = defaultdict(dict)
  for zipcode in zip_reminders_map:
      warnings = generate_warnings(get_weather(zipcode))
      reminder_list = zip_reminders_map[zipcode]
      for reminder in reminder_list:
          if reminder.warning_event in warnings.keys():
              emails[(reminder.user.username, reminder.user.email)][zipcode] = warnings[reminder.warning_event]
              reminder.reminder_sent = datetime.now()
              reminder.save()
  response = {'emails_sent':[]}
  for user_id, email in emails:
      body = "Dear %s,\n\n" % user_id
      for zipcode in emails[(user_id, email)]:
          body += emails[(user_id, email)][zipcode] + "\n"
      body += "\n Best,\nWeather Reminder"
      message = EmailMessage("Weather Reminder", body, to=[email])
      message.send()
      response['emails_sent'].append(email)
  return HttpResponse(json.dumps(response))

def generate_warnings(data):
   warnings = dict()
   try:
       today_weather = data['item']['forecast'][0]
       tomorrow_weather = data['itme']['forecast'][1]
       RAIN_CODES = (200, 201, 202, 210, 211, 212, 221, 230, 231, 232,
                     300, 301, 302, 310, 311, 312, 313, 314, 321,
                     500, 501, 502, 503, 504, 511, 520, 521, 522, 531,
                     900, 901, 902)
       SNOW_CODES = (600, 601, 602, 611, 612, 615, 616, 620, 621, 622,
                     906)
       warning_text = generate_weather_string(data)
       warnings[Reminder.ALWAYS] = warning_text
       if tomorrow_weather['code'] in RAIN_CODES:
           warnings[
               Reminder.RAIN] = warning_text + " It will be raining tomorrow, please remember to take your umbrella."
       if tomorrow_weather['code'] in SNOW_CODES:
           warnings[Reminder.SNOW] = warning_text + " It will be snowing tomorrow, please drive carefully."
       if (float(tomorrow_weather['low']) - float(today_weather['low']) <= -3 or
                       float(tomorrow_weather['high']) - float(today_weather['high']) <= -3):
           warnings[
               Reminder.TEMPDROP3F] = warning_text + " The temperature will drop by more than 3 F, please wear warmer clothes."
       if (float(tomorrow_weather['low']) - float(today_weather['low']) >= 3 or
                       float(tomorrow_weather['high']) - float(today_weather['high']) >= 3):
           warnings[Reminder.TEMPRISE3F] = warning_text + " The temperature will rise by more than 3 F."
   except:
       print(traceback.format_exc())
   return warnings

