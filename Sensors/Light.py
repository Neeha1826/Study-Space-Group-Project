import grovepi

# LIGHT SENSOR METHODS  -----------------------------------------------
# This returns the light as an integer between 0 and 1023

sensor_port = 0 # A0 Port

def readLight():
    light_value = grovepi.analogRead(sensor_port)
    return light_value