import paho.mqtt.client as mqtt
import config


client = mqtt.Client() # Set client as mqtt
client.username_pw_set(config.ACCESS_TOKEN) # Set access token (from config.py)

#connect function
def connect_mqtt():
    try:
        print("Connecting to ThingsBoard")
        client.connect(config.THINGSBOARD_HOST, 1883, 60) #Attempts to connect to things board
        client.loop_start()
        print("Successfully connected to ThingsBoard!") #Print if successfully connected
    except Exception as e:
        print(f"Failed to connect to ThingsBoard: {e}") #Print if failed connected


#disconnect function
def disconnect_mqtt():
    client.loop_stop()
    client.disconnect()
    print("Disconnected from ThingsBoard.")