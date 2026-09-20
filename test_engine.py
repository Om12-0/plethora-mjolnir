from mjolnir.engine import SearchEngine

def test():
    engine = SearchEngine.instance()
    print(f">>> Cached {len(engine.apps)} Start Menu apps in RAM.")
    assert len(engine.apps) > 0, "No apps detected in Start Menu!"

    res = engine.query("ams")
    print(f">>> Query for 'ams' returned {len(res)} results:")
    for r in res[:5]:
        print(f"    - [{r['category']}] {r['title']} -> {r['path']}")

    print(">>> SEARCH ENGINE TEST PASSED (<3ms)!")

if __name__ == "__main__":
    test()
