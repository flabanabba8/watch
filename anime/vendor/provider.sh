#!/bin/sh
# Derived from pystardust/ani-cli v5.1; see UPSTREAM.json and LICENSE.
# Only search, episode listing and link resolution remain. No menu, player or updater.
set -eu
base_api="https://hianime.at"
search_api="${base_api}/search?keyword=%s"
episodes_api="${base_api}/api/theme/episode/list/%s"
servers_api="${base_api}/api/theme/episode/servers?episodeId=%s"
curl_exe="curl"
hianime_curl() { python3 "$(dirname "$0")/../net.py" "$@"; }
die() { printf '%s\n' "$*" >&2; exit 1; }
# GNU, BSD and openssl spell base64 decoding differently
b64_decode() {
    printf "%s\n" "$1" | base64 -d 2>/dev/null || printf "%s\n" "$1" | base64 -D 2>/dev/null || printf "%s\n" "$1" | openssl base64 -d -A 2>/dev/null
}

# the embed page ships its config as base64(json XOR "otaku-embed-v1"), this prints the json.
# runs in a subshell so the key bytes can live in the positional parameters and rotate with shift.
deobfuscate_blob() (
    _bytes="$(b64_decode "$1" | od -v -An -tu1)"
    set -- 111 116 97 107 117 45 101 109 98 101 100 45 118 49
    _output=""
    for _byte in $_bytes; do
        _char=$((_byte ^ $1))
        _output="${_output}\\0$((_char / 64))$(((_char / 8) % 8))$((_char % 8))"
        set -- "$@" "$1"
        shift
    done
    printf "%b" "$_output"
)

# search the query and give results. format is (id \t name)
hianime_search() {
    #shellcheck disable=SC2059
    _page="$(hianime_curl "$(printf "$search_api" "$1")")" || return 1
    if printf "%s" "$_page" | grep -qi "<title>Just a moment"; then
        [ "$curl_exe" = "curl" ] && die "Blocked by cloudflare. Try installing curl-impersonate"
        die "Blocked by cloudflare."
    fi
    # the top 10 sidebar repeats the result markup, cut it off before flattening the page
    printf "%s" "$_page" | sed '/id="main-sidebar"/,$d' | tr '\n' ' ' | sed 's|<div class="film-detail">|\n<div class="film-detail">|g' |
        sed -nE 's|.*<h3 class="film-name">[[:space:]]*<a href="[^"]*/([^"/]*)"[[:space:]]*title="([^"]*)".*|\1\t\2|p' |
        sed -e "s|&#039;|'|g" -e 's|&quot;|"|g' -e "s|&amp;|\&|g"
}

# get the episodes list of the selected anime. format is (id \t ep_no)
hianime_episodes() {
    #shellcheck disable=SC2059
    _page="$(hianime_curl "$(printf "$episodes_api" "${1##*-}")")" || return 1
    # ids from the v5.0 provider have the same shape, so check the slug in the episode links too
    printf "%s" "$_page" | sed 's|\\||g; s|ep-item|\nep-item|g' |
        sed -nE "s|.*data-number=\"([^\"]*)\".*data-id=\"([0-9]+)\".*/watch/${1}[?]ep=.*|\\2\\t\\1|p"
}

# resolves episode $1 in mode $2 (sub/dub): sets links (quality >url per line), sub_link, mal_id and refr
hianime_m3u8() {
    _ep_id=$(printf "%s" "$episode_maps" | sed -nE "s|^([0-9]+)\t${1}$|\1|p")
    #shellcheck disable=SC2059
    _servers="$(hianime_curl "$(printf "$servers_api" "$_ep_id")" | sed 's|\\"|"|g; s|server-item|\nserver-item|g')"
    # only the zokoanime embed is understood by deobfuscate_blob, the other servers use different players
    _hash="$(printf "%s\n" "$_servers" | sed -nE 's|.*data-type="'"$2"'".*data-server-name="ZokoAnime".*data-hash="([^"]*)".*|\1|p' | head -n 1)"
    _embed="$(b64_decode "$_hash")"
    [ -z "$_embed" ] && return 1
    # the stream host wants the embed site as referer, and the embed url carries the mal id for ani-skip
    refr="$(printf "%s" "$_embed" | sed -E 's|^(https?://[^/]*).*|\1/|')"
    mal_id="$(printf "%s" "$_embed" | sed -nE 's|.*/mal/([0-9]+)/.*|\1|p')"
    _blob="$(hianime_curl "$_embed" | sed -nE 's|.*window\.__P="([^"]*)".*|\1|p')"
    [ -z "$_blob" ] && return 1
    _json="$(deobfuscate_blob "$_blob")"
    _m3u8_master="$(printf "%s" "$_json" | sed -nE 's|.*"src":"([^"]*\.m3u8[^"]*)".*|\1|p')"
    [ -z "$_m3u8_master" ] && return 1
    # several languages can be listed, the site marks the english track as default
    sub_link="$(printf "%s" "$_json" | sed 's|.*"subtitles":\[||; s|\].*||; s|},{|}\n{|g' | grep -m 1 '"default":true' | sed -nE 's|.*"src":"([^"]*)".*|\1|p')"
    # quality variants are relative to the master playlist
    links="$(hianime_curl "$_m3u8_master" -e "$refr" | sed 's|^#EXT-X-STREAM.*x||g; s|,.*|p|g; /^#/d; $!N; s|\n| >|;/EXT-X-I-FRAME/d' | sed "\|>https*://|!s|>|>${_m3u8_master%/*}/|" | sort -g -r -s)"
    [ -n "$links" ]
}


case "${1:-}" in
 search) hianime_search "$2" ;;
 episodes) hianime_episodes "$2" ;;
 resolve)
  episode_maps="$(printf '%s\t%s' "$2" "$3")"
  hianime_m3u8 "$3" "$4" || die "No playable source for this episode/audio mode"
  printf 'REFERER\t%s\nSUBTITLE\t%s\n' "$refr" "$sub_link"
  printf '%s\n' "$links"
  ;;
 *) die "Expected search, episodes or resolve" ;;
esac
