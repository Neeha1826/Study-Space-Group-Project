import grovepi

# TEMPERATURE AND HUMIDITY SENSOR METHODS -----------------------------------------------
# This returns the temperature in Celsius, and the Humidity as a percentage

sensor_port = 8 # D8 Port
sensor_type = 0 # 0 = DHT11 (blue), 1 = DHT22 (white)

def readTemp():
    [temp,hum] = grovepi.dht(sensor_port, sensor_type)
    return temp

def readHumid():
    [temp,hum] = grovepi.dht(sensor_port, sensor_type)
    return hum