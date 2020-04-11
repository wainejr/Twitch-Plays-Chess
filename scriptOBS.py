import os

import obspython as obs

abs_path = os.path.dirname(os.path.abspath(__file__))
curr_url = ""
file_input  = ""
interval    = 30
source_name = ""


def update_curr_url(source, new_url):
    try:
        settings = obs.obs_data_create()
        obs.obs_data_set_string(settings, "url", new_url)
        obs.obs_source_update(source, settings)
        obs.obs_data_release(settings)

    except Exception as e :
        obs.script_log(obs.LOG_WARNING, str(e))
        obs.remove_current_callback()


# ------------------------------------------------------------

def update_text():
    global abs_path
    global curr_url
    global file_input
    global interval
    global source_name

    source = obs.obs_get_source_by_name(source_name)
    if source is not None:
        # Tries to find the file in relative location
        filename = file_input
        if(not os.path.exists(file_input)):
            # Tries to find file with absolute location
            filename = os.path.join(abs_path, file_input)

        if(os.path.exists(filename)):
            with open(filename, 'r') as f:
                url = f.read()
                if(url != curr_url):
                    update_curr_url(source, url)

        obs.obs_source_release(source)

def refresh_pressed(props, prop):
    update_text()

# ------------------------------------------------------------

def script_description():
    return ""


def script_update(settings):
    global file_input
    global interval
    global source_name

    file_input  = obs.obs_data_get_string(settings, "file_input")
    interval    = obs.obs_data_get_int(settings, "interval")
    source_name = obs.obs_data_get_string(settings, "source")

    obs.timer_remove(update_text)

    if file_input != "" and source_name != "":
        obs.timer_add(update_text, interval * 1000)


def script_defaults(settings):
    obs.obs_data_set_default_int(settings, "interval", 30)


def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_text(
        props, "file_input", "Read from", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_int(
        props, "interval", "Update Interval (seconds)", 5, 3600, 1)

    p = obs.obs_properties_add_list(props, "source", "URL Source", 
        obs.OBS_COMBO_TYPE_EDITABLE, obs.OBS_COMBO_FORMAT_STRING)

    sources = obs.obs_enum_sources()

    if sources is not None:
        for source in sources:
            source_id = obs.obs_source_get_unversioned_id(source)
            if(source_id == 'browser_source'):
                name = obs.obs_source_get_name(source)
                obs.obs_property_list_add_string(p, name, name)

        obs.source_list_release(sources)

    obs.obs_properties_add_button(props, "button", "Refresh", refresh_pressed)
    return props