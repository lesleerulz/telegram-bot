# keep_alive.py
from flask import Flask
from threading import Thread
import logging
import os # For accessing PORT environment variable if set by Render/hosting

# Use a logger (optional, but good for seeing pings)
# You might want to configure it further if you want these logs in a specific format/file
# For simplicity, using a basic name.
ka_logger = logging.getLogger("keep_alive")
# Basic logging setup for keep_alive if not configured by main script early enough
if not ka_logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


app = Flask('')

@app.route('/')
def home():
    ka_logger.info("Keep-alive endpoint '/' was pinged.")
    return "File Share Bot is alive!"

def run_flask_app():
  try:
    # Render and some other platforms set a PORT environment variable they expect you to use
    port = int(os.environ.get("PORT", 8080)) # Default to 8080 if PORT not set
    ka_logger.info(f"Starting Flask keep-alive server on host 0.0.0.0, port {port}...")
    app.run(host='0.0.0.0', port=port)
    ka_logger.info("Flask keep-alive server has stopped.") # Should not be reached if running indefinitely
  except Exception as e:
    ka_logger.error(f"Flask keep-alive server failed to start or crashed: {e}", exc_info=True)

def keep_alive():
    """Starts the Flask app in a separate daemon thread."""
    ka_logger.info("Initializing keep_alive thread...")
    flask_thread = Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    ka_logger.info("Keep_alive thread started.")
