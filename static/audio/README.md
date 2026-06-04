# Audio assets

Drop the notification chime here as **`ding.mp3`**.

It's played by the notification bell (`notifications/templates/notifications/_bell.html`)
whenever a real-time notification arrives. If the file is missing, notifications
still work — they just arrive silently (playback is wrapped in try/catch).
