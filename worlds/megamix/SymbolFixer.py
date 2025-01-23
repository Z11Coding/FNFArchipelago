import re
from .Translator import transliterate


def unicode_to_plain_text(text):
    mapping = {
        '＋': '+',
        '～': '~',
        '♂': 'maleSign',
        '♀': 'femaleSign',
        '♠': 'spade',
        '♣': 'club',
        '♥': 'heart',
        '♦': 'diamond',
        '♪': 'note',
        '♫': 'notes',
        '∞': 'inf',
        '☀': 'sun',
        '☁': 'cloud',
        '☂': 'umbrella',
        '☃': 'snowman',
        '☄': 'comet',
        '＊': '*',
        '★': '*',
        '☆': '*',
        '◎': 'ring',
        '☎': 'telephone',
        '☏': 'telephone',
        '☑': 'checkBox',
        '☒': '[x]',
        '×': 'x',
        '☞': '>',
        '☜': '<',
        '☝': '^',
        '☟': 'v',
        '　': ' '

        # Add more mappings for special characters here
    }

    special_characters = set(mapping.keys())

    plain_text = []
    word_buffer = ''

    for char in text:
        if char in special_characters:
            if word_buffer:
                plain_text.append(word_buffer)
                word_buffer = ''
            plain_text.append(mapping[char])
        elif char.isalnum() or 128 > ord(char) >= 33:
            word_buffer += char
        elif char.isspace():
            if word_buffer:
                plain_text.append(word_buffer)
                word_buffer = ''
            plain_text.append(' ')

    # Add the last buffered word
    if word_buffer:
        plain_text.append(word_buffer)

    final_text = ''.join(plain_text)

    # Clean up extra spaces created by replacement
    final_text = re.sub(r'\s+', ' ', final_text).strip()

    # Remove any trailing spaces
    final_text = final_text.rstrip()

    return final_text


def replace_non_ascii_with_space(text):
    return ''.join(char if ord(char) < 128 or char == '_' else ' ' for char in text)


def special_char_removal(text):
    # Remove apostrophes, commas, and quotation marks
    cleaned_text = text.replace("'", "").replace(",", "").replace('"', "")

    # Replace multiple spaces with a single space
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)

    # Strip any leading or trailing spaces
    return cleaned_text.strip()


# Function to replace symbols in specific base game songs
def replace_symbols(song_name):

    # Replace infinity with nothing
    song_name = song_name.replace("∞", " ")
    # Replace symbols
    song_name = re.sub(r'([◎★♣＊☆])', ' ', song_name)
    # Remove music notes
    song_name = song_name.replace("♪", "")

    return song_name


# These songs have special symbols, they get removed specifically to make a cleaner item name for base game songs.
# Modded songs don't go through the same replacement as they might comprise only the symbols being removed
offending_songs = [
    "Beware of the Miku Miku Germs♪",
    "I'll Miku-Miku You♪ (For Reals)",
    "Clover♣Club",
    "Monochrome∞Blue Sky",
    "Fire◎Flower",
    "Sadistic.Music∞Factory",
]


# Function to fix song names, so they don't crash Unity games
def fix_song_name(song_name):

    # Clean up base game songs specifically
    if song_name in offending_songs:
        song_name = replace_symbols(song_name)

    # Clean up song names
    cleaned_song_name = unicode_to_plain_text(song_name)  # Try to convert unicode to plain text
    cleaned_song_name = transliterate(cleaned_song_name)
    cleaned_song_name = replace_non_ascii_with_space(cleaned_song_name)  # After conversion, replace any remainders with blanks
    cleaned_song_name = special_char_removal(cleaned_song_name)
    return cleaned_song_name
