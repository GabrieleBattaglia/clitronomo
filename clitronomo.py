# CLITRONOMO BY GABRIELE BATTAGLIA
# Un metronomo da riga di comando.
# Data di concepimento 9 settembre 2025.

import numpy as np
import sounddevice as sd
import threading, time, json

VERSION="1.1.0 - settembre 2025"
SAMPLE_RATE = 44100 
COMANDI = {
    'g', 's', 'b', '?', '0', '1', '2', '3',
    'v1', 'v2', 'v3',
    'f1', 'f2', 'f3',
    'a1', 'a2', 'a3',
    'd1', 'd2', 'd3',
    'l1', 'l2', 'l3',
    'ms', 'm', 'ml', 'mc',
    'q','i',
}
HELP_STRING = """
--- Menu Comandi Clitronomo ---

>> CONTROLLO
  g           - Avvia il metronomo
  s           - Ferma il metronomo
  q           - Esci dal programma

>> RITMO
  b <bpm>     - Imposta i BPM (es. b 120 o b120)
  t <n/d>     - Imposta il tempo (es. t 7/8)
  0,1,2,3     - Attiva/Disattiva Suddivisioni (0=off, 1=8vi, 2=16vi, 3=32vi)

>> PARAMETRI SUONO (n = 1:Accento, 2:Beat, 3:Sub)
  l<n> <ms>   - Durata del beep (es. l1 100)
  v<n> <vol>  - Volume 0-100 (es. v2 70)
  f<n> <hz>   - Frequenza (es. f3 600)
  a<n> <ms>   - Attack in ms (es. a1 5)
  d<n> <ms>   - Decay in ms (es. d2 50)
  i           - Mostra lo stato attuale dei parametri

>> GESTIONE PRESET
  m           - Mostra i preset salvati
  ms <nome>   - Salva il preset corrente
  ml <nome>   - Carica un preset
  mc <nome>   - Cancella un preset
---------------------------------
"""
def genera_suono_mono_int16(config):
    """
    Genera solo il campione audio del "beep" udibile, senza silenzio.
    Utilizza attack e decay in millisecondi.
    """
    # --- 1. Calcola la lunghezza del beep udibile in campioni ---
    beep_duration_s = config["beep_duration_ms"] / 1000.0
    beep_samples = int(SAMPLE_RATE * beep_duration_s)
    
    if beep_samples <= 0:
        return np.array([], dtype=np.int16)

    # --- 2. Calcola i campioni per l'inviluppo A/D/S in base ai MS ---
    attack_ms = config.get("attack_ms", 10)
    decay_ms = config.get("decay_ms", 50)

    attack_samples = int(SAMPLE_RATE * (attack_ms / 1000.0))
    decay_samples = int(SAMPLE_RATE * (decay_ms / 1000.0))

    # Controllo di sicurezza per evitare che A+D superino la durata totale
    total_envelope_samples = attack_samples + decay_samples
    if total_envelope_samples > beep_samples:
        # Se l'inviluppo è più lungo del suono, lo ridimensioniamo
        ratio = beep_samples / total_envelope_samples if total_envelope_samples > 0 else 0
        attack_samples = int(attack_samples * ratio)
        decay_samples = int(decay_samples * ratio)
    
    sustain_samples = beep_samples - attack_samples - decay_samples
    if sustain_samples < 0: sustain_samples = 0
    
    # --- 3. Genera l'onda e applica l'inviluppo ---
    t = np.linspace(0., beep_duration_s, beep_samples, endpoint=False)
    wave_float = np.sin(2. * np.pi * config["frequency_hz"] * t)
    
    envelope = np.concatenate([
        np.linspace(0, 1, attack_samples) if attack_samples > 0 else np.array([]),
        np.ones(sustain_samples),
        np.linspace(1, 0, decay_samples) if decay_samples > 0 else np.array([])
    ])
    
    final_wave_float = config["volume_perc"]/100.0 * wave_float * envelope
    final_wave_float = np.clip(final_wave_float, -1.0, 1.0)
    beep_int16 = (final_wave_float * 32767.0).astype(np.int16)
    
    # --- 4. Restituisce direttamente il beep generato ---
    return beep_int16
class Metronome:
    def __init__(self, bpm=120, time_signature="4/4"):
        self.is_dirty = False
        self.current_preset_id = None
        self.session_measure_count = 0
        self.session_start_time = None
        self.bpm = bpm
        self.time_signature = time_signature
        self.beats_per_measure, self.note_value = map(int, self.time_signature.split('/'))

        # Attributi per la gestione dello stream e del timing
        self.stream = None
        self.is_running = threading.Event()

        # Attributi per la logica della callback
        self.current_beat = 0
        self.samples_per_beat = 0
        self.sample_index_in_beat = 0
        self.config_subdivision = {
            "beep_duration_ms": 10, "volume_perc": 15, "attack_ms": 2,
            "decay_ms": 8, "frequency_hz": 1030.0
        }
        self.subdivision_level = 0
        self.active_buffer = np.array([], dtype=np.int16) # Il nastro audio in riproduzione
        self.pending_buffer = None # Il nastro audio che prepariamo quando cambia un parametro
        self.buffer_lock = threading.Lock() # Un "semaforo" per gestire i nastri in modo sicuro
        self.playback_index = 0 # La nostra "puntina" sul nastro
        self.config_accento = {
            "beep_duration_ms": 70, "volume_perc": 50, "attack_ms": 5,
            "decay_ms": 8, "frequency_hz": 915.0
        }
        self.config_tick = {
            "beep_duration_ms": 40, "volume_perc": 35, "attack_ms": 5,
            "decay_ms": 12, "frequency_hz": 550.0
        }
                # Pre-generiamo i suoni
        self.accent_sound = None
        self.tick_sound = None
        self.generate_sounds()
    def display_status(self, preset_manager):
        """Mostra una tabella riassuntiva di tutte le impostazioni correnti."""
        print("\n--- Stato Attuale Clitronomo ---")
        
        # Stato del Preset
        preset_id_str = str(self.current_preset_id) if self.current_preset_id else "Default"
        preset_name = ""
        # Ecco le righe corrette!
        if self.current_preset_id and preset_id_str in preset_manager.data['presets']:
            preset_name = f" ({preset_manager.data['presets'][preset_id_str]['name']})"
        
        modified_status = " (modificato)" if self.is_dirty else ""
        print(f"Preset Attivo: {preset_id_str}{preset_name}{modified_status}")
        
        # Stato del Ritmo
        sub_map = {0: "off", 2: "ottavi", 4: "sedicesimi", 8: "trentaduesimi"}
        sub_text = sub_map.get(self.subdivision_level, 'sconosciuto')
        print(f"Ritmo: {self.bpm} BPM  |  Tempo: {self.beats_per_measure}/{self.note_value}  |  Suddivisioni: {sub_text}")
        
        # Tabella Parametri Suono
        print("---------------------------------------------------------")
        print(f"{'Parametro':<12} | {'Accento (1)':<12} | {'Beat (2)':<12} | {'Sub (3)':<12}")
        print("---------------------------------------------------------")
        
        param_keys = [
            ('Durata (l)', 'beep_duration_ms', 'ms'),
            ('Volume (v)', 'volume_perc', '%'),
            ('Freq (f)', 'frequency_hz', 'Hz'),
            ('Attack (a)', 'attack_ms', 'ms'),
            ('Decay (d)', 'decay_ms', 'ms')
        ]
                
        for label, key, unit in param_keys:
            v1 = self.config_accento.get(key, 'N/A')
            v2 = self.config_tick.get(key, 'N/A')
            v3 = self.config_subdivision.get(key, 'N/A')
            print(f"{label:<12} | {str(v1):<10} {unit:<2} | {str(v2):<10} {unit:<2} | {str(v3):<10} {unit:<2}")
        
        print("---------------------------------------------------------")
# All'interno della classe Metronome
    
    def reset_to_default(self):
        """Resetta il metronomo alle impostazioni di fabbrica."""
        print("\nNessun preset rimanente. Caricamento impostazioni di default.")
        self.bpm = 120
        self.time_signature = "4/4"
        self.beats_per_measure, self.note_value = 4, 4
        self.subdivision_level = 0
        self.current_preset_id = None
        self.is_dirty = False # Lo stato di default non è "modificato"
        self._request_buffer_rebuild()
    def set_state(self, state, preset_id):
        """Applica uno stato salvato al metronomo."""
        try:
            self.bpm = state['bpm']
            num, den = map(int, state['time_signature'].split('/'))
            self.beats_per_measure = num
            self.note_value = den
            self.subdivision_level = state['subdivision_level']
            self.config_accento = state['config_accento']
            self.config_tick = state['config_tick']
            self.config_subdivision = state['config_subdivision']
            
            self.current_preset_id = preset_id
            self.is_dirty = False # Lo stato ora corrisponde a un preset salvato
            
            print(f"Stato del preset ID{preset_id} applicato.")
            self._request_buffer_rebuild()
            
        except KeyError as e:
            print(f"\nERRORE: Dati mancanti o corrotti nel preset. Chiave non trovata: {e}")
    def _generate_measure_buffer(self):
        """
        "Renderizza" un'intera battuta in un unico array numpy,
        mixando accento, beat e suddivisioni.
        """
        # 1. Calcoliamo la durata di una semiminima (1/4) in base ai BPM
        samples_per_quarter_note = (60.0 / self.bpm) * SAMPLE_RATE
        # 2. Calcoliamo la durata del nostro beat in base al denominatore
        #    (es. una croma, 1/8, dura la metà di una semiminima)
        samples_per_beat = int(samples_per_quarter_note * (4 / self.note_value))
        samples_per_measure = samples_per_beat * self.beats_per_measure
        
        # 2. Crea un "nastro" vuoto (silenzio)
        measure_buffer = np.zeros(samples_per_measure, dtype=np.float32)

        # 3. Genera i singoli "beep" (accento, tick e suddivisione)
        accent_beep = genera_suono_mono_int16(self.config_accento).astype(np.float32) / 32767.0
        tick_beep = genera_suono_mono_int16(self.config_tick).astype(np.float32) / 32767.0
        sub_beep = genera_suono_mono_int16(self.config_subdivision).astype(np.float32) / 32767.0
        
        # 4. "Disegna" i suoni sul nastro, beat per beat
        for beat_num in range(self.beats_per_measure):
            start_pos = beat_num * samples_per_beat
            
            # Scegli e disegna il beat principale (accento o tick)
            main_beep = accent_beep if beat_num == 0 else tick_beep
            end_pos = min(start_pos + len(main_beep), samples_per_measure)
            length_to_add = end_pos - start_pos
            measure_buffer[start_pos:end_pos] += main_beep[:length_to_add]
            
            # --- NUOVO: Disegna le suddivisioni ---
            if self.subdivision_level > 1 and len(sub_beep) > 0:
                samples_per_sub = int(samples_per_beat / self.subdivision_level)
                # Partiamo da 1 per saltare la suddivisione 0, che è il beat principale
                for sub_num in range(1, self.subdivision_level):
                    sub_start_pos = start_pos + (sub_num * samples_per_sub)
                    
                    # Evita di scrivere fuori dal buffer
                    if sub_start_pos >= samples_per_measure:
                        break
                    
                    # Mixa il suono della suddivisione
                    sub_end_pos = min(sub_start_pos + len(sub_beep), samples_per_measure)
                    sub_length_to_add = sub_end_pos - sub_start_pos
                    
                    if sub_length_to_add > 0:
                        measure_buffer[sub_start_pos:sub_end_pos] += sub_beep[:sub_length_to_add]
        
        # 5. Normalizza per evitare clipping e converti in int16
        peak = np.max(np.abs(measure_buffer))
        if peak > 1.0:
            measure_buffer /= peak
            
        return (measure_buffer * 32767.0).astype(np.int16)    
    def generate_sounds(self):
        """Genera e adatta i suoni alla durata esatta di un beat."""
        self.samples_per_beat = int((60.0 / self.bpm) * SAMPLE_RATE)
        self.accent_sound = genera_suono_mono_int16(self.config_accento)
        self.tick_sound = genera_suono_mono_int16(self.config_tick)
    def update_sound_param(self, command, value):
        """Aggiorna un parametro del suono per accento(1), tick(2) o suddivisione(3)."""
        param_map = {
            'v': 'volume_perc', 'f': 'frequency_hz',
            'a': 'attack_ms', 'd': 'decay_ms', 'l': 'beep_duration_ms'
        }
        cmd_key = ''.join(filter(str.isalpha, command))
        target_char = ''.join(filter(str.isdigit, command))
        param_key = param_map.get(cmd_key)

        if not param_key or target_char not in ('1', '2', '3'):
            print("\nComando parametro suono non valido.")
            return

        try:
            val = int(value)
            
            # Logica di validazione
            if param_key == 'volume_perc' and target_char == '3':
                if val >= self.config_tick['volume_perc'] or val >= self.config_accento['volume_perc']:
                    print(f"\nERRORE: Volume suddivisione ({val}) deve essere minore di quello di beat e accento.")
                    return
            
            if param_key == 'beep_duration_ms' and target_char == '3':
                if val >= self.config_tick['beep_duration_ms'] or val >= self.config_accento['beep_duration_ms']:
                    print(f"\nERRORE: Durata suddivisione ({val}ms) deve essere minore di quella di beat e accento.")
                    return

            configs = {'1': self.config_accento, '2': self.config_tick, '3': self.config_subdivision}
            target_dict = configs[target_char]

            # Controllo a+d <= l
            attack = val if param_key == 'attack_ms' else target_dict['attack_ms']
            decay = val if param_key == 'decay_ms' else target_dict['decay_ms']
            duration = val if param_key == 'beep_duration_ms' else target_dict['beep_duration_ms']
            if attack + decay > duration:
                print(f"\nERRORE: La somma di Attack ({attack}ms) e Decay ({decay}ms) non può superare la Durata ({duration}ms).")
                return
                
            target_dict[param_key] = val
            print(f"\n{param_key} per {'accento' if target_char == '1' else 'tick' if target_char == '2' else 'suddivisione'} impostato a {val}.")
            self.is_dirty = True
            self._request_buffer_rebuild()

        except (ValueError, IndexError):
            print(f"\nValore non valido: '{value}'. Inserire un numero intero.")
    def _audio_callback(self, outdata, frames, time, status):
        """Callback corretta che gestisce il loop e lo swap dei buffer."""
        if status:
            print(status, flush=True)

        needed_frames = frames
        written_frames = 0
        
        with self.buffer_lock:
            while written_frames < needed_frames:
                buffer_len = len(self.active_buffer)
                if buffer_len == 0:
                    outdata.fill(0)
                    return

                # Se abbiamo finito la battuta, è il momento di agire
                if self.playback_index >= buffer_len:
                    # 1. CONTROLLO PRIORITARIO: C'è un nuovo buffer in attesa?
                    if self.pending_buffer is not None:
                        # Sì, facciamo lo SWAP!
                        self.active_buffer = self.pending_buffer
                        self.pending_buffer = None
                        buffer_len = len(self.active_buffer)
                    self.session_measure_count += 1
                    # 2. Ora mandiamo in loop l'indice di riproduzione
                    self.playback_index = 0

                # Calcola quanti frame copiare in questo ciclo
                remaining_in_buffer = buffer_len - self.playback_index
                frames_to_write = min(needed_frames - written_frames, remaining_in_buffer)
                
                # Copia i dati
                outdata[written_frames : written_frames + frames_to_write] = \
                    self.active_buffer[self.playback_index : self.playback_index + frames_to_write].reshape(-1, 1)

                # Aggiorna gli indici
                self.playback_index += frames_to_write
                written_frames += frames_to_write
    def _request_buffer_rebuild(self):
        """Chiede di generare un nuovo buffer e lo mette in attesa."""
        new_buffer = self._generate_measure_buffer()
        with self.buffer_lock:
            self.pending_buffer = new_buffer
    def set_bpm(self, new_bpm):
        if 5 <= new_bpm <= 1000:
            self.bpm = new_bpm
            print(f"\nBPM impostati a {self.bpm}. La modifica sarà attiva dalla prossima battuta.")
            self.is_dirty = True
            self._request_buffer_rebuild()
        else:
            print(f"\nValore BPM non valido.")

    def set_subdivision(self, level_code):
        """
        Imposta il livello di suddivisione per ogni beat.
        0=off, 1=ottavi(2), 2=sedicesimi(4), 3=trentaduesimi(8).
        Se il livello è già attivo, lo disattiva.
        """
        # Mappa corretta: codice input -> suddivisioni per BEAT
        level_map = {1: 2, 2: 4, 3: 8}
        
        if level_code == 0:
            new_level = 0
        elif level_code in level_map:
            target_level = level_map[level_code]
            # Se il livello richiesto è già attivo, lo disattiviamo. Altrimenti lo impostiamo.
            new_level = 0 if self.subdivision_level == target_level else target_level
        else:
            print(f"\nCodice suddivisione '{level_code}' non valido. Usa 0, 1, 2, 3.")
            return

        self.subdivision_level = new_level
        
        # Mappa per i messaggi all'utente
        status_map = {0: "off", 2: "ottavi (2 per beat)", 4: "sedicesimi (4 per beat)", 8: "trentaduesimi (8 per beat)"}
        print(f"\nSuddivisioni impostate a: {status_map.get(self.subdivision_level, 'off')}")
        self.is_dirty = True
        self._request_buffer_rebuild()
    def start(self):
        if self.is_running.is_set():
            return
        print("Metronomo avviato.")
        self.session_measure_count = 0
        self.session_start_time = time.perf_counter()
        # Genera il primo nastro audio prima di partire
        self.active_buffer = self._generate_measure_buffer()
        self.is_running.set()
        self.stream = sd.OutputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype=np.int16,
            callback=self._audio_callback, latency='low'
        )
        self.stream.start()

    def stop(self):
        if not self.is_running.is_set():
            return
        if self.session_start_time is not None:
            elapsed_seconds = time.perf_counter() - self.session_start_time
            # Calcoliamo ore, minuti e secondi
            minutes, seconds = divmod(elapsed_seconds, 60)
            hours, minutes = divmod(minutes, 60)
            # Formattiamo il tempo e stampiamo il report
            # 1. Creiamo una lista vuota per contenere le parti del tempo
            time_parts = []

            # 2. Aggiungiamo le ore solo se sono maggiori di zero
            if int(hours) > 0:
                time_parts.append(f"{int(hours)} {'ora' if int(hours) == 1 else 'ore'}")

            # 3. Aggiungiamo i minuti solo se sono maggiori di zero
            if int(minutes) > 0:
                time_parts.append(f"{int(minutes)} {'minuto' if int(minutes) == 1 else 'minuti'}")

            # 4. Aggiungiamo i secondi se sono maggiori di zero, o se è l'unica unità di tempo
            if int(seconds) > 0 or not time_parts:
                time_parts.append(f"{int(seconds)} {'secondo' if int(seconds) == 1 else 'secondi'}")

            # 5. Uniamo le parti in una stringa ben formattata
            if len(time_parts) > 2:
                # Es: "1 ora, 5 minuti e 10 secondi"
                formatted_time = ", ".join(time_parts[:-1]) + f" e {time_parts[-1]}"
            elif len(time_parts) == 2:
                # Es: "5 minuti e 10 secondi"
                formatted_time = " e ".join(time_parts)
            else:
                # Es: "10 secondi"
                formatted_time = time_parts[0]
            print(f"\nSessione terminata: {self.session_measure_count} battute in {formatted_time}.")
    
            # Azzeriamo il tempo di partenza
            self.session_start_time = None        
        self.is_running.clear()
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.playback_index = 0
        print("\nMetronomo fermato.")
    def set_time_signature(self, numerator, denominator):
        """Imposta un nuovo tempo e richiede l'aggiornamento del buffer audio."""
        # Aggiungiamo un controllo di validità
        if not (0 < numerator < 33 and denominator in (2, 4, 8, 16, 32)):
            print(f"\nTempo non valido: {numerator}/{denominator}. Numeratore (1-32), Denominatore (2,4,8,16,32).")
            return

        self.beats_per_measure = numerator
        self.note_value = denominator
        
        print(f"\nTempo impostato a {self.beats_per_measure}/{self.note_value}. La modifica sarà attiva dalla prossima battuta.")
        self.is_dirty = True
        self._request_buffer_rebuild()
    def get_state(self):
        """Raccoglie tutte le impostazioni correnti in un dizionario."""
        return {
            "bpm": self.bpm,
            "time_signature": f"{self.beats_per_measure}/{self.note_value}",
            "subdivision_level": self.subdivision_level,
            "config_accento": self.config_accento,
            "config_tick": self.config_tick,
            "config_subdivision": self.config_subdivision
        }

# NUOVA CLASSE
class PresetManager:
    """Gestisce la lettura, scrittura e manipolazione dei preset da file JSON."""
    def __init__(self, filename="clitronomo_presets.json"):
        self.filename = filename
        # Struttura dati che conterrà i nostri preset in memoria
        self.data = {
            "last_preset_id": None,
            "presets": {}
        }
        self._load_presets()
    def _load_presets(self):
        """Carica i preset dal file JSON. Se non esiste, lo crea."""
        try:
            with open(self.filename, 'r') as f:
                self.data = json.load(f)
            print(f"File preset '{self.filename}' caricato. Trovati {len(self.data['presets'])} metronomi salvati.")
        except FileNotFoundError:
            print(f"File preset non trovato. Ne creo uno nuovo: '{self.filename}'")
            self._save_presets()
        except (json.JSONDecodeError, KeyError):
            print(f"ERRORE: Il file preset '{self.filename}' è corrotto o malformato. Verrà creato un nuovo file vuoto.")
            # Resettiamo alla struttura di default e salviamo
            self.data = {"last_preset_id": None, "presets": {}}
            self._save_presets()
    def _save_presets(self):
        """Salva lo stato attuale di TUTTI i preset nel file JSON."""
        with open(self.filename, 'w') as f:
            json.dump(self.data, f, indent=1)
    def list_presets(self, active_preset_id=None): # <-- 1. Accetta un nuovo argomento opzionale
        """Mostra una lista paginata dei preset salvati."""
        if not self.data['presets']:
            print("\nNessun preset salvato.")
            return

        presets_list = sorted([(int(pid), pdata['name']) for pid, pdata in self.data['presets'].items()])
        
        page_size = 10
        total_pages = (len(presets_list) + page_size - 1) // page_size
        current_page = 1

        while True:
            print("\n--- Preset Salvati ---")
            start_index = (current_page - 1) * page_size
            end_index = start_index + page_size
            
            for pid, name in presets_list[start_index:end_index]:
                # --- 2. Logica per l'indicatore ---
                indicator = ""
                # Confrontiamo gli ID dopo averli resi stringhe per sicurezza
                if active_preset_id is not None and str(pid) == str(active_preset_id):
                    indicator = "* " # L'indicatore che vuoi mostrare
                
                # Stampiamo con l'indicatore (o uno spazio vuoto per allineare)
                print(f"  {indicator:<2}{name}")
                # ---------------------------------

            if total_pages <= 1:
                break

            print(f"\nPagina {current_page}/{total_pages}")
            choice = input("Premi Invio per la pagina successiva, 'q' per uscire: ").lower()
            
            if choice == 'q':
                break
            
            current_page += 1
            if current_page > total_pages:
                break
    def _find_matches(self, search_term):
        """Motore di ricerca interno: trova preset in modo case-insensitive."""
        search_term_lower = search_term.lower()
        matches = []
        for pid, pdata in self.data['presets'].items():
            if search_term_lower in pdata['name'].lower():
                matches.append((pid, pdata))
        return matches
    def save_preset(self, name, state, preset_id=None):
        """Assegna un ID, lo antepone al nome, salva il preset e aggiorna il file."""
        
        if preset_id:
            # CASO 1: Stiamo sovrascrivendo un preset esistente.
            # L'ID ci è già stato fornito.
            preset_id_str = str(preset_id)
        else:
            # CASO 2: Stiamo creando un nuovo preset.
            # Dobbiamo trovare il prossimo ID libero.
            next_id = 1
            existing_ids = {int(k) for k in self.data['presets'].keys()}
            while next_id in existing_ids:
                next_id += 1
            preset_id_str = str(next_id)

        # A questo punto, abbiamo un preset_id_str valido in entrambi i casi.
        # La costruzione del nome finale è la stessa.
        # Ci aspettiamo che `name` sia il nome pulito, senza prefissi.
        final_name = f"ID{preset_id_str} {name}"
        
        # Ora salviamo i dati
        self.data['presets'][preset_id_str] = {
            "name": final_name,
            "state": state
        }
        
        print(f"\nPreset salvato con nome '{final_name}'.")
        
        # Scriviamo le modifiche sul file
        self._save_presets()
        return preset_id_str
    def find_preset(self, search_term):
        """Usa il motore di ricerca per trovare e caricare un preset."""
        matches = self._find_matches(search_term)
                
        if len(matches) == 0:
            print(f"\nNessun preset trovato contenente '{search_term}'.")
            return None
        elif len(matches) > 1:
            print("\nCorrispondenza ambigua. Trovati più preset:")
            for pid, pdata in matches:
                print(f"  - {pdata['name']}")
            print("Per favore, sii più specifico.")
            return None
        else: # Esattamente 1 risultato
            pid, pdata = matches[0]
            print(f"\nPreset trovato: '{pdata['name']}'. Caricamento in corso...")
            return pid, pdata['state']
    
    def delete_preset(self, search_term, active_preset_id=None):
        """
        Cerca e cancella un preset.
        Restituisce un valore per indicare al main cosa fare dopo:
        - Se viene cancellato il preset attivo:
            - Restituisce l'ID del primo preset rimanente da caricare.
            - Restituisce 'DEFAULT' se non ci sono più preset.
        - Altrimenti non restituisce nulla.
        """
        matches = self._find_matches(search_term)

        if len(matches) == 0:
            print(f"\nNessun preset trovato contenente '{search_term}'.")
            return None
        elif len(matches) > 1:
            # ... (la gestione dei match ambigui non cambia) ...
            return None
        
        pid_to_delete, pdata_to_delete = matches[0]
        preset_name = pdata_to_delete['name']
        
        try:
            confirm = input(f"Sei sicuro di voler cancellare il preset '{preset_name}'? (s/n): ").lower()
            if confirm == 's':
                del self.data['presets'][pid_to_delete]
                self._save_presets()
                print(f"Preset '{preset_name}' cancellato con successo.")

                # --- NUOVA LOGICA ---
                if pid_to_delete == active_preset_id:
                    if not self.data['presets']: # Non ci sono più preset?
                        return 'DEFAULT' # Istruzione per caricare il default
                    else:
                        # Prendi il primo preset rimasto, ordinalo per ID
                        first_remaining_id = sorted(self.data['presets'].keys(), key=int)[0]
                        return first_remaining_id # Istruzione per caricare questo ID
            else:
                print("Cancellazione annullata.")
        except (KeyboardInterrupt, EOFError):
            print("\nCancellazione annullata.")
        
        return None # Non fare nulla se non è stato cancellato il preset attivo
    def set_last_used(self, preset_id):
        """Imposta l'ID dell'ultimo preset usato e salva."""
        self.data['last_preset_id'] = preset_id
        self._save_presets()
    def get_last_used_preset(self):
        """Restituisce l'ID e lo stato dell'ultimo preset usato, se esiste."""
        last_id = self.data.get('last_preset_id')
        if last_id and str(last_id) in self.data['presets']:
            preset_data = self.data['presets'][str(last_id)]
            print(f"Caricamento automatico dell'ultimo preset: '{preset_data['name']}'")
            return str(last_id), preset_data['state']
        return None, None

def main():
    """Funzione principale che avvia il metronomo e gestisce l'input dell'utente."""
    preset_manager = PresetManager()
    clitronomo = Metronome(bpm=120, time_signature="4/4")

    last_id, last_state = preset_manager.get_last_used_preset()
    if last_state:
        clitronomo.set_state(last_state, last_id)

    clitronomo.display_status(preset_manager)
    print("\n--- CLITRONOMO ---")
    print(f"Versione {VERSION}\n\t by Gabriele Battaglia IZ4APU\n")
    print("\t\t--- Digita '?' per la lista dei comandi.")
    
    while True:
        command_full = input("Clitronomo > ").strip().lower()

        if not command_full:
            continue

        parts = command_full.split(maxsplit=1)
        command = parts[0]
        value = parts[1] if len(parts) > 1 else None

        if command == 'g':
            clitronomo.start()
        elif command == 's':
            clitronomo.stop()
        elif command == 'i':
            clitronomo.display_status(preset_manager)
        elif command.startswith('b'):
            try:
                if command == 'b' and value is not None:
                    new_bpm = int(value)
                else:
                    new_bpm = int(command[1:])
                clitronomo.set_bpm(new_bpm)
            except (ValueError, IndexError):
                print("Formato non valido. Usa b<bpm> o b <bpm>, es: b120")
        elif command == 'm':
            preset_manager.list_presets(clitronomo.current_preset_id)
        elif command == 'mc':
            search_term = value
            if search_term is None:
                search_term = input("Cancella preset contenente (lascia vuoto per annullare): ")

            if search_term:
                # Passiamo l'ID attivo e catturiamo l'istruzione di ritorno
                instruction = preset_manager.delete_preset(search_term, clitronomo.current_preset_id)

                if instruction:
                    if instruction == 'DEFAULT':
                        clitronomo.reset_to_default()
                    else: # Altrimenti è un nuovo ID da caricare
                        new_id_to_load = instruction
                        new_state = preset_manager.data['presets'][new_id_to_load]['state']
                        clitronomo.set_state(new_state, new_id_to_load)

                    clitronomo.display_status(preset_manager) # Mostra il nuovo stato
        elif command == 'ml':
            search_term = value
            if search_term is None:
                search_term = input("Carica preset contenente (lascia vuoto per annullare): ")
            if search_term:
                found_preset = preset_manager.find_preset(search_term) # <-- CORRETTO
                if found_preset:
                    preset_id, preset_state = found_preset
                    clitronomo.set_state(preset_state, preset_id)
        elif command == 'ms':
            if value is None:
                try:
                    name = input("Nome del preset da salvare: ")
                    if not name:
                        print("Salvataggio annullato. Nessun nome fornito.")
                        continue
                except (KeyboardInterrupt, EOFError):
                    print("\nSalvataggio annullato.")
                    continue
            else:
                name = value

            current_state = clitronomo.get_state()
            preset_id = preset_manager.save_preset(name, current_state) # <-- CORRETTO
            clitronomo.is_dirty = False
            clitronomo.current_preset_id = preset_id
            
        elif command == 't' and value is not None:
            try:
                if '/' in value:
                    num, den = map(int, value.split('/'))
                    clitronomo.set_time_signature(num, den)
                else:
                    raise ValueError("Formato non valido")
            except (ValueError, IndexError):
                print(f"Formato non valido per il tempo. Usa t <num>/<den>, es: t 4/4")
        elif command in ('0', '1', '2', '3'):
            try:
                code = int(command)
                clitronomo.set_subdivision(code)
            except ValueError:
                print(f"Errore interno nell'interpretare il comando '{command}'")
        elif command in COMANDI and value is not None:
             clitronomo.update_sound_param(command, value)
        elif command == '?':
            print(HELP_STRING)
        elif command == 'q':
            if clitronomo.is_dirty:
                while True:
                    choice = input("\nHai modifiche non salvate. Cosa vuoi fare?\n [S]ovrascrivi preset, [N]uovo nome, [E]sci senza salvare, [A]nnulla: ").lower()
                    if choice == 's':
                        if clitronomo.current_preset_id:
                            print(f"Sovrascrivo il preset ID{clitronomo.current_preset_id}...")
                            current_state = clitronomo.get_state()
                            preset_name_full = preset_manager.data['presets'][clitronomo.current_preset_id]['name']
                            # Estraiamo solo il nome senza "IDx "
                            preset_name_clean = " ".join(preset_name_full.split(' ')[1:])
                            preset_manager.save_preset(preset_name_clean, current_state, preset_id=clitronomo.current_preset_id) # <-- CORRETTO
                            break 
                        else:
                            print("Nessun preset attualmente caricato da sovrascrivere. Salva con un nuovo nome.")
                            continue
                    elif choice == 'n':
                        name = input("Nome del nuovo preset: ")
                        if name:
                            current_state = clitronomo.get_state()
                            preset_manager.save_preset(name, current_state) # <-- CORRETTO
                            break
                        else:
                            print("Nome non valido.")
                            continue
                    elif choice == 'e':
                        break 
                    elif choice == 'a':
                        print("Operazione annullata.")
                        break
                    else:
                        print("Scelta non valida.")
                
                if choice == 'a':
                    continue 
            
            print("Salvataggio stato e chiusura di Clitronomo...")
            preset_manager.set_last_used(clitronomo.current_preset_id)
            break
        else:
            print(f"Comando '{command_full}' non riconosciuto. Digita '?' per la lista.")
if __name__ == "__main__":
    main()