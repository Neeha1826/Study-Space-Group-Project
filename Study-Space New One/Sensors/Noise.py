import grovepi

# NOISE SENSOR METHODS  -----------------------------------------------
# This returns the noise as an integer between 0 and 1023

sensor_port = 1 # A1 Port

def readNoise():
    noise_value = grovepi.analogRead(sensor_port)
    return noise_value