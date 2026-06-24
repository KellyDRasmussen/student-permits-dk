# Country classifications for VAN66 citizenship labels (English names as returned by Statbank BULK).
# Global North/South and Western are approximate and contested — edge cases are noted inline.

EU27 = {
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus",
    "Czech Republic", "Denmark", "Estonia", "Finland", "France",
    "Germany", "Greece", "Hungary", "Ireland", "Italy",
    "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands",
    "Poland", "Portugal", "Romania", "Slovakia", "Slovenia",
    "Spain", "Sweden",
}

G7 = {
    "Canada", "France", "Germany", "Italy",
    "Japan", "United Kingdom", "USA",
}

G20 = {
    "Argentina", "Australia", "Brazil", "Canada", "China",
    "France", "Germany", "India", "Indonesia", "Italy",
    "Japan", "Mexico", "Russia", "Saudi Arabia", "South Africa",
    "South Korea", "Turkey", "United Kingdom", "USA",
} | EU27

# Global North: roughly the UN's "more developed regions" + East Asian high-income economies.
# Russia and Turkey included (geographically / economically developed), Belarus included.
_NON_EU_EUROPE = {
    "Albania", "Andorra", "Belarus", "Bosnia and Herzegovina",
    "Iceland", "Kosovo", "Liechtenstein", "Moldova", "Monaco",
    "Montenegro", "Northern Ireland", "Republic of North Macedonia",
    "Norway", "Russia", "San Marino", "Serbia",
    "Serbia and Montenegro", "Switzerland", "Turkey", "Ukraine",
    "United Kingdom", "Vatican City State",
}

GLOBAL_NORTH = EU27 | _NON_EU_EUROPE | {
    "Canada", "USA",
    "Australia", "New Zealand",
    "Japan", "South Korea", "Israel", "Singapore", "Taiwan",
}

# Western: Danmarks Statistik definition of "vestlige lande" —
# EU27 + EEA/European microstates + Canada, USA, Australia, New Zealand.
# Notably excludes: Balkans, Ukraine, Russia, Turkey, Japan, South Korea, Israel.
WESTERN = EU27 | {
    "Andorra", "Iceland", "Liechtenstein", "Monaco",
    "Norway", "San Marino", "Switzerland", "United Kingdom", "Vatican City State",
    "Canada", "USA",
    "Australia", "New Zealand",
}

# Ordered for the UI
DIMENSIONS = {
    "G7 / Non-G7": ("G7", "Non-G7", G7),
    "G20 / Non-G20": ("G20", "Non-G20", G20),
    "Global North / South": ("Global North", "Global South", GLOBAL_NORTH),
    "Western / Non-Western": ("Western", "Non-Western", WESTERN),
}


def get_group(country: str, dimension: str) -> str:
    label_in, label_out, group_set = DIMENSIONS[dimension]
    return label_in if country in group_set else label_out
