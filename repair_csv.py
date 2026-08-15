import csv

input_file = "data/raw/menu_dataset.csv"
output_file = "data/raw/menu_dataset_fixed.csv"

with open(input_file, "r", encoding="utf-8") as infile, \
     open(output_file, "w", encoding="utf-8", newline="") as outfile:

    reader = csv.reader(
        infile,
        delimiter=",",
        quotechar='"',
        escapechar="\\"
    )

    writer = csv.writer(
        outfile,
        quoting=csv.QUOTE_ALL
    )

    for row in reader:
        writer.writerow(row)

print("CSV repaired")