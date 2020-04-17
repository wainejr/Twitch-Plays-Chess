import os
import time

import obspython as obs

source_name  = ""
interval = 3600


# ------------------------------------------------------------

def deactivate_and_activate_source():
    global source_name
    global interval

    source = obs.obs_get_source_by_name(source_name)
    if(source is not None):
        print("Deactivating source", source_name, flush=True)
        obs.obs_source_set_enabled(source, False)
        time.sleep(1)
        print("Activating source", source_name, flush=True)
        obs.obs_source_set_enabled(source, True)

    obs.obs_source_release(source)

def switch_pressed(props=None, prop=None):
    deactivate_and_activate_source()

# ------------------------------------------------------------

def script_description():
    return 'Activate and deactivate source. Useful for refreshing browser (only way I found)'\
        + '\n\nby Waine'


def script_update(settings):
    global source_name
    global interval

    source_name  = obs.obs_data_get_string(settings, "source_name")
    interval = obs.obs_data_get_int(settings, "interval")

    obs.timer_remove(switch_pressed)

    if source_name != "":
        obs.timer_add(switch_pressed, interval*1000)


def script_defaults(settings):
    obs.obs_data_set_default_int(settings, "interval", 1200)


def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_text(
        props, "source_name", "Source", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_int(
        props, "interval", "Switch Interval (seconds)", 1, 7200, 1)

    obs.obs_properties_add_button(props, "button", "Switch", switch_pressed)
    return props