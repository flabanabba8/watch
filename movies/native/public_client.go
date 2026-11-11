// Public HTTPS-only client for the source bridge. Media playback is a separate mpv process.
package main

import (
	"context"
	"errors"
	"net"
	"net/http"
	"time"
)

func publicIP(ip net.IP) bool {
	if ip == nil || !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() {
		return false
	}
	if v4 := ip.To4(); v4 != nil {
		if v4[0] == 0 || (v4[0] == 100 && v4[1] >= 64 && v4[1] <= 127) ||
			(v4[0] == 192 && v4[1] == 0 && (v4[2] == 0 || v4[2] == 2)) ||
			(v4[0] == 198 && (v4[1] == 18 || v4[1] == 19)) ||
			(v4[0] == 198 && v4[1] == 51 && v4[2] == 100) ||
			(v4[0] == 203 && v4[1] == 0 && v4[2] == 113) {
			return false
		}
	} else if v6 := ip.To16(); v6 != nil && v6[0] == 0x20 && v6[1] == 0x01 && v6[2] == 0x0d && v6[3] == 0xb8 {
		return false
	}
	return true
}

func publicDial(ctx context.Context, network, address string) (net.Conn, error) {
	host, port, err := net.SplitHostPort(address)
	if err != nil || port != "443" {
		return nil, errors.New("public HTTPS endpoint required")
	}
	addresses, err := net.DefaultResolver.LookupIPAddr(ctx, host)
	if err != nil || len(addresses) == 0 {
		return nil, errors.New("provider DNS lookup failed")
	}
	for _, addr := range addresses {
		if !publicIP(addr.IP) {
			return nil, errors.New("provider resolved to a non-public address")
		}
	}
	dialer := &net.Dialer{Timeout: 10 * time.Second, KeepAlive: 30 * time.Second}
	for _, addr := range addresses {
		conn, err := dialer.DialContext(ctx, network, net.JoinHostPort(addr.IP.String(), port))
		if err == nil {
			return conn, nil
		}
	}
	return nil, errors.New("provider connection failed")
}

type publicTransport struct{ next http.RoundTripper }

func (t publicTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if req.URL == nil || req.URL.Scheme != "https" || req.URL.Hostname() == "" || req.URL.User != nil ||
		(req.URL.Port() != "" && req.URL.Port() != "443") || req.URL.Fragment != "" {
		return nil, errors.New("public HTTPS endpoint required")
	}
	return t.next.RoundTrip(req)
}

func newPublicClient() *http.Client {
	transport := &http.Transport{Proxy: nil, DialContext: publicDial, ForceAttemptHTTP2: true,
		MaxIdleConns: 20, IdleConnTimeout: 30 * time.Second, TLSHandshakeTimeout: 10 * time.Second}
	return &http.Client{Transport: publicTransport{next: transport}, Timeout: 12 * time.Second}
}
