import geoip2.database

with geoip2.database.Reader("/etc/geoip/GeoLite2-City.mmdb") as reader:
    r = reader.city("8.8.8.8")
    print(r.country.iso_code)
    print(r.city.name)
    print(r.location.latitude, r.location.longitude)

