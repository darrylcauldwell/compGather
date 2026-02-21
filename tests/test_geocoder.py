from app.services.geocoder import _haversine


def test_haversine_london_to_manchester():
    # London (51.5074, -0.1278) to Manchester (53.4808, -2.2426) ~163 miles
    distance = _haversine(51.5074, -0.1278, 53.4808, -2.2426)
    assert 160 < distance < 170


def test_haversine_same_point():
    distance = _haversine(51.5074, -0.1278, 51.5074, -0.1278)
    assert distance < 0.01


def test_haversine_london_to_birmingham():
    # London to Birmingham ~101 miles
    distance = _haversine(51.5074, -0.1278, 52.4862, -1.8904)
    assert 95 < distance < 110
