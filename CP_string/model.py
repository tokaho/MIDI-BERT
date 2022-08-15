import numpy as np
import pickle
import utils
import miditoolkit
from skyline import Skyline
from p_tqdm import p_map


class CP(object):
    def __init__(self, dict, midi_paths, task, max_len):
        # load dictionary
        self.dict = dict
        self.skyline = Skyline(dict)
        self.task = task
        self.max_len = max_len
        self.midi_paths = midi_paths
        self.event2word, self.word2event = pickle.load(open(dict, "rb"))
        # pad word: ['Bar <PAD>', 'Position <PAD>', 'Pitch <PAD>', 'Duration <PAD>']
        self.pad_word = [
            self.event2word[etype]["%s <PAD>" % etype] for etype in self.event2word
        ]

    def extract_events(self, input_path):
        note_items_all, tempo_items = utils.read_items(input_path)
        # note_items should be contain multiple list of each individual track
        # ===================================================================
        midi_obj = miditoolkit.midi.parser.MidiFile(input_path)
        if len(midi_obj.time_signature_changes) == 0:
            return None

        midi_obj = utils.convert_string_quartets(midi_obj)
        if not utils.is_string_quartets(midi_obj):
            # print(input_path, "Not a string quartet")
            return None

        numerator = midi_obj.time_signature_changes[0].numerator
        if self.task == "custom" or self.task == "skyline":
            for note_items in note_items_all:
                for i in note_items:
                    # Add 'Program' to each raw token
                    i.Program = utils.Type2Program(midi_obj, i.Type)
                    # Add 'TimeSignature' to each raw token
                    i.TimeSignature = utils.raw_time_signature(midi_obj, i.start)
            # Also add 'TimeSignature' to each tempo token
            for i in tempo_items:
                i.TimeSignature = utils.raw_time_signature(midi_obj, i.start)
        # ===================================================================
        events_all = []
        for note_items in note_items_all:
            if len(note_items) == 0:
                events_all.append(None)
                continue
            note_items = utils.quantize_items(note_items)
            max_time = note_items[-1].end
            items = tempo_items + note_items

            # ===================================================================
            multiple_ts_at = [ts.time for ts in midi_obj.time_signature_changes]
            groups = utils.group_items(
                items,
                max_time,
                utils.DEFAULT_TICKS_PER_BEAT * numerator,
                multiple_ts_at,
            )
            events = utils.item2event(groups, self.task, numerator, midi_obj)
            # ===================================================================
            events_all.append(events)

        return events_all

    def padding(self, data):
        pad_len = self.max_len - len(data)
        for _ in range(pad_len):
            data.append(self.pad_word)
        return data

    def _prepare_data(self, path):
        # extract events
        total_words, total_ys = [], []
        try:
            events_all = self.extract_events(path)
            all_words = []
            for events in events_all:
                for note_tuple in events:
                    nts = []
                    for e in note_tuple:
                        e_text = f"{e.name} {e.value}"
                        nts.append(self.event2word[e.name][e_text])
                    all_words.append(nts)
        except:
            return None
        for idx, events in enumerate(events_all):
            if events == None or len(events) == 0:
                return None
            # events to words
            words = []
            for note_tuple in events:
                nts = []
                for e in note_tuple:
                    e_text = f"{e.name} {e.value}"
                    nts.append(self.event2word[e.name][e_text])
                words.append(nts)
                # if self.task == "custom":
                #     slice_words = []
                #     for i in range(0, len(words), self.max_len):
                #         slice_words.append(words[i : i + self.max_len])
                #     if len(slice_words[-1]) < self.max_len:
                #         slice_words[-1] = self.padding(slice_words[-1])
            if self.task == "skyline":
                print(path, len(all_words), len(words))
                try:
                    slice_words, slice_ys = self.skyline.generate(all_words, words, idx)
                    total_words.append(list(slice_words))
                    total_ys.append(list(slice_ys))
                except:
                    pass
            # total_words.append(words)
            # total_ys.append(ys)

        return total_words, total_ys

    def prepare_data(self):
        all_words, all_ys = [], []
        for result in p_map(self._prepare_data, self.midi_paths):
            if result is not None:
                all_words += result[0]
                all_ys += result[1]

        all_words = np.array(all_words).astype(np.int64)
        if self.task == "skyline":
            all_ys = np.array(all_ys).astype(np.int64)
        return all_words, all_ys
