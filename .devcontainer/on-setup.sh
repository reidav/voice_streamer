setup() {
    sudo apt update
    sudo apt install libgstreamer1.0-0 \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-ugly
    pip3 install --user -r requirements.txt
}