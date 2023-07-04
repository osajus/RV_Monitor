import bmp180
import time
import board
import busio
import os
import ipaddress
import wifi
import socketpool
import ssl
import smtp_circuitpython
import digitalio
from secrets import secrets



HIGH_TEMP = 83  # Fahrenheit
POLL_FREQ = 30   # seconds
MAIL_DELAY = 600.0  # seconds

i2c = busio.I2C(board.GP17, board.GP16)

bmp = bmp180.BMP180(i2c)

bmp.sea_level_pressure = 1013.25
#bmp.sea_level_pressure = 1016.8

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

last_violation = time.monotonic()

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
led.value = False

def send_mail(tempF):
    mail_to = secrets['gmail_to']
    mail_subject="Temp Alert!  Temp in RV is at %0.1f" % tempF
    mail_body= "Temp Alert\r\n"
    mail_body += "IP Address is "+str(wifi.radio.ipv4_address)

    smtp = smtp_circuitpython.SMTP(host=SMTP_SERVER, port=SMTP_PORT,
                pool=pool, ssl_context=ssl_context, use_ssl = True,
                username=secrets['gmail_user'],password=secrets['gmail_password'],
                debug = True)
    smtp.to(mail_to)
    smtp.body("Subject: "+mail_subject+"\r\n\r\n"+mail_body)
    smtp.quit()
    return None

def get_tempF():
    tempC = bmp.temperature
    tempF = tempC * (9/5) + 32
    return tempF



try: 
    wifi.radio.connect(secrets['CIRCUITPY_WIFI_SSID'], 
                       secrets['CIRCUITPY_WIFI_PASSWORD'])
    led.value = True
except Exception as e:
    print("Error", e)

pool = socketpool.SocketPool(wifi.radio)
ssl_context = ssl.create_default_context()

print("My IP:", wifi.radio.ipv4_address)

ipv4 = ipaddress.ip_address("8.8.4.4")
print("Google pinged at: %f ms" % (wifi.radio.ping(ipv4) * 1000))




while True:
    tempF = get_tempF()
    #print("\nTemperature: %0.1f C" % bmp.temperature)
    #print("Pressure: %0.1f hPa" % bmp.pressure)
    #print("Altitude = %0.2f meters" % bmp.altitude)
    print(tempF)    
    now = time.monotonic()
    
    if ((tempF > HIGH_TEMP) and (now - last_violation > MAIL_DELAY)):
        print("Temp is high: %0.1f F. Sending email: " % tempF)
        last_violation = time.monotonic()
        send_mail(tempF)

    time.sleep(POLL_FREQ)

