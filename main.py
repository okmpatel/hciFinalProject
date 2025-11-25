import asyncio
import colorsys
from quart import Quart, render_template_string, request
from kasa import SmartBulb
import RPi.GPIO as GPIO

# --- CONFIGURATION ---
PIR_PIN = 17
BULB_IPS = [
    "192.168.1.33",
    "192.168.1.36"
]

# --- SETUP ---
app = Quart(__name__)
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

bulbs = [SmartBulb(ip) for ip in BULB_IPS]
motion_active = False

# --- HELPER FUNCTIONS ---
async def update_all_bulbs():
    """Refreshes the state of all bulbs."""
    for bulb in bulbs:
        try:
            await bulb.update()
        except Exception as e:
            print(f"Update error {bulb.host}: {e}")

async def set_bulbs_state(state: bool):
    for bulb in bulbs:
        try:
            if state:
                await bulb.turn_on()
            else:
                await bulb.turn_off()
        except Exception as e:
            print(f"State error {bulb.host}: {e}")

async def set_bulbs_brightness(level: int):
    for bulb in bulbs:
        try:
            # Ensure bulb is on so the command takes effect
            if not bulb.is_on:
                await bulb.turn_on()
            await bulb.set_brightness(int(level))
        except Exception as e:
            print(f"Brightness error {bulb.host}: {e}")

async def set_bulbs_color(hex_color: str):
    """Converts HEX (#ff0000) to HSV and sets bulb color."""
    # Convert hex to RGB (0-1 range)
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    # Convert RGB to HSV
    # colorsys returns h,s,v in 0-1 range. Kasa needs H:0-360, S:0-100, V:0-100
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    
    kasa_h = int(h * 360)
    kasa_s = int(s * 100)
    kasa_v = int(v * 100)

    for bulb in bulbs:
        try:
            if not bulb.is_on:
                await bulb.turn_on()
            await bulb.set_hsv(kasa_h, kasa_s, kasa_v)
        except Exception as e:
            print(f"Color error {bulb.host}: {e}")

async def set_bulbs_temp(temp: int):
    """Sets White Temperature (2500K - 6500K)."""
    for bulb in bulbs:
        try:
            if not bulb.is_on:
                await bulb.turn_on()
            await bulb.set_color_temp(int(temp))
        except Exception as e:
            print(f"Temp error {bulb.host}: {e}")

# --- PIR SENSOR LOOP ---
async def pir_loop():
    global motion_active
    print("PIR Sensor Loop Started...")
    while True:
        if GPIO.input(PIR_PIN):
            if not motion_active:
                print("Motion! Lights ON.")
                motion_active = True
                await set_bulbs_state(True)
                await asyncio.sleep(20) # Keep lights on for 20s
                print("Timer done. Lights OFF.")
                await set_bulbs_state(False)
                motion_active = False
        await asyncio.sleep(0.1)

# --- WEB SERVER ROUTES ---

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; text-align: center; padding: 10px; background: #222; color: white; }
        .card { background: #333; padding: 20px; border-radius: 15px; max-width: 400px; margin: auto; }
        
        button { padding: 15px; width: 45%; margin: 5px; font-size: 16px; border: none; border-radius: 8px; cursor: pointer; color: white; }
        .btn-on { background-color: #4CAF50; }
        .btn-off { background-color: #f44336; }
        
        label { display: block; margin-top: 15px; font-weight: bold; }
        input[type=range] { width: 100%; margin: 10px 0; }
        
        /* Make the color input look like a big button */
        input[type=color] { border: none; width: 100%; height: 50px; cursor: pointer; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Kasa Control Center</h2>
        <p>Status: <span style="color:#aaa">{{ status }}</span></p>
        
        <form action="/toggle" method="post">
            <button name="state" value="on" class="btn-on">ON</button>
            <button name="state" value="off" class="btn-off">OFF</button>
        </form>

        <form action="/brightness" method="post">
            <label>Brightness</label>
            <input type="range" min="1" max="100" name="level" onchange="this.form.submit()">
        </form>

        <form action="/color" method="post">
            <label>Color Picker</label>
            <input type="color" name="hex_color" value="#ffffff" onchange="this.form.submit()">
        </form>

        <form action="/temperature" method="post">
            <label>White Temperature (Warm - Cool)</label>
            <input type="range" min="2500" max="6500" step="100" name="temp" onchange="this.form.submit()">
        </form>
    </div>
</body>
</html>
"""

@app.route('/')
async def home():
    status = "Motion Active" if motion_active else "Ready"
    return await render_template_string(HTML_PAGE, status=status)

@app.route('/toggle', methods=['POST'])
async def toggle():
    form = await request.form
    state = form.get('state') == 'on'
    await set_bulbs_state(state)
    return await render_template_string(HTML_PAGE, status="Switched")

@app.route('/brightness', methods=['POST'])
async def brightness():
    form = await request.form
    level = form.get('level')
    await set_bulbs_brightness(level)
    return await render_template_string(HTML_PAGE, status=f"Brightness {level}%")

@app.route('/color', methods=['POST'])
async def color():
    form = await request.form
    hex_val = form.get('hex_color')
    await set_bulbs_color(hex_val)
    return await render_template_string(HTML_PAGE, status="Color Set")

@app.route('/temperature', methods=['POST'])
async def temperature():
    form = await request.form
    temp = form.get('temp')
    await set_bulbs_temp(temp)
    return await render_template_string(HTML_PAGE, status=f"Temp {temp}K")

@app.before_serving
async def startup():
    # Initialize connection to bulbs
    await update_all_bulbs()
    app.add_background_task(pir_loop)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)