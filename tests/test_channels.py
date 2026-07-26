from retrostation_player.channels import parse_m3u


def test_parse_ersatztv_style_m3u():
    playlist = '''#EXTM3U
#EXTINF:-1 tvg-id="7" tvg-chno="107" tvg-name="Classic TV" tvg-logo="http://host/logo.png" group-title="ErsatzTV",Classic TV
http://host/iptv/channel/7.m3u8
'''
    channels = parse_m3u(playlist)
    assert len(channels) == 1
    assert channels[0].id == "7"
    assert channels[0].number == "107"
    assert channels[0].name == "Classic TV"
    assert channels[0].url == "http://host/iptv/channel/7.m3u8"
