# Deezer Record

This project is a Python script which allow you to record the output of music streaming service, cutting the audio stream for each song.

It's initially done for [Deezer](www.deezer.fr), extracting song title and artist from the title of the browser window, but it can probably be updated for any site like YouTube, Spotify, etc.

## How does it work ?

This script mainly rely on three binaries : **Xorg**, **Pulseaudio** and **Lame**

To record the audio stream, the script move the audio output of one application to a dedicated muted channel of pulseaudio which write its input in raw format. This raw file (that you can inspect with Audacity for example) is then converted to _good_ MP3 with lame. This technique allow stereo and high-quality (if you change lame to a flac or any other encoder).

Xorg is used mainly to detect when a song ended and when the whole playlist has been recorded. To detect these, we use the title of the browser window which must change to reflect the current playing song. Because of that, it's heavily recommanded to use a dedicated window, with no tabs.

## Dependancies

First, you need some Python packages (available through pip):
 * `python-slugify` (and not `slugify`)
 * `python-xlib`

As explain above you need an Xorg server with two utilities:
 * `xprop` which come with Xorg I think
 * `xwininfo` that you probably have to install manually

`xwininfo` is only used to get the window ID of the browser window (which is not returned by xprop) to use xprop without mouse input. In fact, `xprop` is not really necessary as the window title is also returned by xwininfo. Maybe I will remove the `xprop` dependancy one day.

Then you must have **Pulseaudio** installed. This is quite the case for anyone using an Ubuntu/Debian based distrib (I don't know for the other). Pulseaudio must come (I hope) with `pacmd`, `pactl` and `parec`, if not, install them. If you want, it's absolutely not necessary, you can also install `pavucontrol` to check that the browser output is actually moved, or that your browser actually plays something.
I think that the same result can be achieve (maybe easier) with JACK, but as it's not installed by default on many distrib and that it's a mess to use it with pulseaudio also installed (go to hell pulseaudio's autolaunch), I didn't handle it. Feel free to fork !

Finally, for encoding, I use `lame` that you probably have to install manually. This is an arbitrary choice, you can easily change the command used to encode.

## How to use it

Prepare all the things that you need:
 * A browser window on your favorite music streaming site
 * A playlist (of at least 2 songs)
 * An active _loop_ button to make sure the playlist go back to the beginning at the end

Then launch the script :
```
    python streamrecord
```
You can use `-h` to see the different options.

If you didn't pass any argument, you will be prompted to click on the player window. This is to grab the window ID used with `xprop` to get the window title.

Then, you have to launch the player (if it's not already playing), and then press `Enter` in the terminal window. Don't worry, the whole first song will be recorded but at the end (that's why you have to check the _loop_ switch).

If you have more than one window that is actually doing any sound, the script will prompt you to choose the right audio output. It's likely the one with the highest ID. Choose the right one, and press `Enter`.

The sound must stop, because the audio output is moved to the muted channel. Let's the script work for a few seconds (~5s) and check that it displays the right title and the right artist. If all is alright, you can pass the first song (as you probably missed the beginning), it will be re-recorded at the end. Now, let's the script run.

The script must stop when it recorded all the playlist. You can detect this because the audio come back!

That's all, you can close your browser.
