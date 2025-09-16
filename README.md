# Clitronomo
**Versione 1.1.0**

Un metronomo da riga di comando (CLI) efficiente, leggero e interamente controllabile da tastiera, scritto in Python. Progettato per musicisti, sviluppatori e chiunque preferisca la velocità e la semplicità del terminale.

---

## Caratteristiche Principali

* **Interfaccia a Riga di Comando**: Nessuna GUI. Tutte le operazioni avvengono tramite comandi testuali, garantendo minime risorse di sistema e massima velocità.
* **Gestione di Preset**: Salva, carica, elenca e cancella facilmente le tue configurazioni preferite. I preset sono salvati in un file `clitronomo_presets.json` leggibile e facilmente modificabile.
* **Accessibilità**: Il programma è stato sviluppato pensando all'accessibilità. Essendo un'applicazione testuale, è pienamente compatibile con **screen reader** (come NVDA, JAWS, VoiceOver) e **display Braille**, garantendo un'esperienza utente completa a persone non vedenti e ipovedenti.
* **Configurazione Audio Dettagliata**: Personalizza la frequenza, il volume, la durata, l'attack e il decay per ogni suono (accento, beat e suddivisione).

---

## Installazione

Clitronomo richiede Python 3 e due librerie esterne.

1.  Assicurati di avere Python installato.
2.  Installa le dipendenze necessarie tramite pip:
    ```bash
    pip install numpy sounddevice
    ```

---

## Utilizzo

Per avviare il programma, esegui lo script dalla cartella del progetto:

```bash
python clitronomo.py
````

All'avvio, verrà caricato l'ultimo preset utilizzato o, in assenza di preset, verrà avviato un metronomo di default a 120 BPM in 4/4.

-----

## Riferimento Comandi

### Controlli di Base

| Comando | Spiegazione                  | Esempio       |
| :------ | :--------------------------- | :------------ |
| `g`     | Avvia il metronomo.          | `g`           |
| `s`     | Ferma il metronomo.          | `s`           |
| `i`     | Mostra lo stato corrente.    | `i`           |
| `?`     | Mostra la lista dei comandi. | `?`           |
| `q`     | Esce dal programma.          | `q`           |

### Ritmo

| Comando       | Spiegazione                                    | Esempio       |
| :------------ | :--------------------------------------------- | :------------ |
| `b <bpm>`     | Imposta i Beats Per Minute.                    | `b 120`       |
| `t <n/d>`     | Imposta il tempo (es. 7/8).                    | `t 7/8`       |
| `0`, `1`, `2`, `3` | Attiva/Disattiva le suddivisioni (0=off, 1=ottavi, 2=sedicesimi, 3=trentaduesimi). | `2` |

### Parametri Suono (`<n>` = 1:Accento, 2:Beat, 3:Sub)

| Comando     | Spiegazione                          | Esempio       |
| :---------- | :----------------------------------- | :------------ |
| `l<n> <ms>` | Imposta la durata del suono in ms.   | `l1 100`      |
| `v<n> <vol>`| Imposta il volume (0-100).           | `v2 70`       |
| `f<n> <hz>` | Imposta la frequenza in Hz.          | `f3 880`      |
| `a<n> <ms>` | Imposta l'attack in ms.              | `a1 5`        |
| `d<n> <ms>` | Imposta il decay in ms.              | `d2 50`       |

### Gestione Preset

| Comando      | Spiegazione                                          | Esempio          |
| :----------- | :--------------------------------------------------- | :--------------- |
| `m`          | Mostra la lista dei preset salvati.                  | `m`              |
| `ms <nome>`  | Salva la configurazione corrente come nuovo preset.  | `ms Esercizio A` |
| `ml <nome>`  | Carica un preset cercandolo per nome.                | `ml Esercizio`   |
| `mc <nome>`  | Cancella un preset cercandolo per nome.              | `mc Lento`       |

-----

## Sviluppatori

  * **Gabriele Battaglia** (IZ4APU) - Concept e sviluppo principale.
  * **Partner di Programmazione (Gemini)** - Code review, debugging e implementazione di nuove feature.

-----

## Idee per Sviluppi Futuri (Roadmap)

  * **Pattern Ritmici (Comando `p`)**: Introdurre un comando `p` per definire pattern complessi, specificando quali beat e suddivisioni devono suonare e quali no (es. ritmi di clave, terzine, ecc.).
  * **Tap Tempo**: Implementare un comando `tap` che permetta di impostare i BPM premendo ripetutamente Invio a tempo.
  * **Supporto Suoni `.wav`**: Permettere agli utenti di associare file audio personalizzati (es. suoni di batteria) all'accento, al beat e alle suddivisioni.
  * **Modalità Allenamento**: Aggiungere feature specifiche per lo studio, come l'aumento graduale dei BPM in un dato intervallo di tempo o la disattivazione audio di una o più battute per testare la propria stabilità ritmica.

<!-- end list -->
