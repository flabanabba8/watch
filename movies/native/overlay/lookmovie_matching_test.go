package providers

import "testing"

func TestLookMovieMatchingRequiresUnambiguousTitleAndYear(t *testing.T) {
	results := []lookmovieSearchResult{
		{Slug: "older", Title: "Example Film", Year: "1980"},
		{Slug: "newer", Title: "Example Film", Year: "2020"},
	}
	if got := matchLookMovieResult(results, "", "Example Film", "2020"); got != "newer" {
		t.Fatal("expected exact year")
	}
	if got := matchLookMovieResult(results, "", "Example Film", "2010"); got != "" {
		t.Fatal("must not choose a different year")
	}
	if got := matchLookMovieResult(results, "", "Example Film", ""); got != "" {
		t.Fatal("ambiguous title must not select first")
	}
	if got := matchLookMovieResult(results[:1], "", "Example Film", ""); got != "older" {
		t.Fatal("expected unique title")
	}
}
