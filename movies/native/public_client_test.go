package main

import (
	"context"
	"io"
	"net"
	"net/http"
	"strings"
	"testing"
)

type dummyTransport struct{ called bool }

func (d *dummyTransport) RoundTrip(*http.Request) (*http.Response, error) {
	d.called = true
	return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader("ok"))}, nil
}

func TestPublicIPRejectsPrivateAndSpecialAddresses(t *testing.T) {
	if publicIP(net.IPv4zero) || publicIP(net.IPv6loopback) || publicIP(net.IPv6linklocalallnodes) {
		t.Fatal("non-public address accepted")
	}
	if !publicIP(net.IPv4(8, 8, 8, 8)) {
		t.Fatal("public address rejected")
	}
}

func TestTransportRejectsInsecureOrCredentialURLs(t *testing.T) {
	next := &dummyTransport{}
	transport := publicTransport{next: next}
	for _, value := range []string{"http://example.com/", "https://user:fixture@example.com/", "https://example.com:8443/"} {
		req, err := http.NewRequest("GET", value, nil)
		if err != nil {
			t.Fatal(err)
		}
		if _, err = transport.RoundTrip(req); err == nil {
			t.Fatal("unsafe request accepted")
		}
	}
	if next.called {
		t.Fatal("unsafe request reached transport")
	}
}

func TestLocalhostDialIsRejected(t *testing.T) {
	if conn, err := publicDial(context.Background(), "tcp", net.JoinHostPort("localhost", "443")); err == nil {
		conn.Close()
		t.Fatal("loopback resolution accepted")
	}
}
