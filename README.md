# Ream: A Paper Manager

## Setup
1. Install dependencies:

```
pip3 install -r requirements.txt
```

2. Create a config file by running:

```
cp config.default.yaml config.yaml
```

Edit `config.yaml` as appropriate.

3. Create the SQLite database:

```
./create-db
```

This creates an empty database in the location specified by `config.yaml`.

4. Run the app (will use port 5538 by default)

```
python3 app.py
```

## Credits
Icons were taken from https://primer.style/octicons/.
