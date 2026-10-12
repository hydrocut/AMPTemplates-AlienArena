# AMPTemplates-AlienArena — Alien Arena: Warriors Of Mars dedicated server for AMP

**AMP Generic Module** template for the **Alien Arena: Warriors Of Mars** dedicated server
(`alienarena-ded`), the free arena FPS by COR Entertainment on the CRX engine (Quake 2 lineage,
<https://alienarena.org/>). Written for TeamKit, a free French game host, on 11 Oct 2026.
No Alien Arena template was found, neither at CubeCoders nor in the community.

> Résumé en français à la fin du fichier.

## Version and download

| | |
|---|---|
| Game version | **7.72.3** (27 Sep 2026), latest GitHub release of <https://github.com/alienarena/alienarena> on 11 Oct 2026 |
| Server binary | `alienarena-ded`, **compiled during the Update** (`./configure --disable-client`, about 1 min), needs only libc and libm |
| Size | ~1.7 GB installed (`data1/` without the 176 MB of map sources, `arena/`), 20 official maps |
| Download | the tag's source archive from `codeload.github.com` (~1.2 GB, streamed into `tar`, ~1.5 min on the TeamKit host) |

COR Entertainment publishes **no Linux binary** (`unix_dist/INSTALL`: "there is no pre-built
executable"; GitHub releases carry no assets). Debian 13 does ship `alien-arena-server` 7.71.7, but
in `contrib`, with its data (7.71.3) in `non-free`: neither section is enabled in
`cubecoders/ampbase:debian`, and 7.72 brought server-side changes (antilag, tick rate). Both speak
network protocol 36. So `scripts/installer-alienarena.sh`:

1. asks the GitHub API for the latest release tag (keeps the installed version if GitHub does not answer);
2. stops there if that version is already installed (`jeu/.version`);
3. streams the tag's source archive into `tar`, leaving out `data1/maps/mapsrc`, `Tools`, `steam`,
   Windows binaries and project files;
4. builds **only the dedicated server** (`make -C source alienarena-ded`: a plain `make` would also
   build the client's C++ physics library) — `gcc`, `make`, `libc6-dev`, `pkg-config` and `zlib1g-dev`
   come from `Meta.ExtraContainerPackages`, so **the template requires container mode**;
5. installs `jeu/` = `alienarena-ded` + `data1/` + `arena/` + licence files, and swaps it in only when
   everything succeeded.

The whole `data1/` is kept on purpose: the server reads the maps (`.bsp`), but also the player
models (`.iqm`, hit boxes, `server/sv_game.c`), the terrain collision files
(`maps/meshes/...`, `qcommon/terrain.c`), the bots (`botinfo/`), and checks
`data1/pics/colormap.pcx` to run "in place" (`qcommon/files.c`).

**Licence.** The code is GPL-2.0-or-later. The game data may be redistributed freely *as a whole and
for use with Alien Arena*; selling or using for profit individual parts needs COR's consent
(`unix_dist/README`, section 8). The data is downloaded from the official repository on each server,
never stored here. `Meta.NoCommercialUsage=True` to stay on the safe side.

## Files

| File | Role |
|---|---|
| `alienarena.kvp`, `alienarena*.json`, `manifest.json` | the AMP template |
| `scripts/AMP_reglages-alienarena.txt` | settings model; AMP renders it to `reglages-alienarena.txt` (`ConfigType: template`). No max-players line: AMP passes `{{$MaxUsers}}` on the command line |
| `scripts/installer-alienarena.sh` | download + build + install (last Update stage) |
| `scripts/lancer-alienarena.sh` | start script (`lancer-alienarena.sh <port> <max players>`) |
| `verifier.py` | pre-push checks, must print `Tout est bon.` |

The three `scripts/` files are fetched from this repository (raw.githubusercontent.com, branch
`main`) at each Update, so **the repository must be public**.

Instance layout: `jeu/` (game, replaced by Updates), `donnees/cor-games/arena/` (the server's own
writable directory, `XDG_DATA_HOME=donnees`: generated config, `perso.cfg`, added maps, bot files),
`cartes-disponibles.txt` (maps found at the last start).

## How the server is started

`/bin/bash lancer-alienarena.sh <port> <max players>`:

1. reads `reglages-alienarena.txt`, checks every value and **makes texts displayable**: the game font
   only has ASCII (`ref_gl/r_ttf.c` masks every byte with `0x7F`), and `"`, `;`, `\` are forbidden in
   server info strings. Accents are transliterated (`é` → `e`, `œ` → `oe`, `—` → `-`, `« x »` → `'x'`),
   `"` → `'`, `;` → `,`, `\` → `/`, with a console notice. Name, admin and website are cut to 63
   characters (`MAX_INFO_VALUE`). Passwords are not altered: one with a space, accent, `"`, `;` or `\`
   (or the word `none`, which the game reads as "no password") stops the start with a French error;
2. lists the maps (`jeu/data1/maps`, `jeu/arena/maps`, `donnees/cor-games/arena/maps`) into
   `cartes-disponibles.txt`; builds the rotation (`sv_maplist`): the AMP list without unknown maps, or,
   when empty, every installed map of the chosen mode (`dm-` for deathmatch / team deathmatch / duel,
   `ctf-`, `tac-`, the prefixes of the game's own menu) in the order of the official `arena/maps.lst`;
3. writes `donnees/cor-games/arena/amp-teamkit.cfg`: the AMP settings, `dmflags` computed from the
   check boxes, `setmaster master.alienarena.org master2.alienarena.org` when listed (as in the
   official `arena/server.cfg`), then `exec perso.cfg`, then `map <start map>`; and `amp-motd.txt`
   (welcome message, `motdfile`, shown centred to each joining player);
4. creates `perso.cfg` once (never overwritten) for any other cvar, read after AMP's values;
5. runs the **bridge** (`PONT`, Python, below) which starts
   `jeu/alienarena-ded +set sys_ansicolor 0 +set logfile 0 +set port <port> +exec amp-teamkit.cfg`.

### Why a bridge: the dedicated server needs a terminal

`main()` of the dedicated build (`source/unix/sys_unix.c`) **exits silently** when its stdin or
stderr is not a TTY ("a terminal with non-blocking input is required"), and AMP gives it pipes. The
bridge opens a pseudo-terminal (echo and output post-processing off), runs the server in it, and:

* passes AMP's console lines to the server (`status`, `kick 3`, `map ctf-frost`, `sv addbot`…);
  lines are cut at 250 bytes, the server reads 256 at most;
* passes the server's lines to AMP, masking the RCON password in `Rcon from` / `Bad rcon from`
  logs (`rcon *** "status"`);
* keeps the **player list**: on each join / leave / kick / timeout line (and every 30 s while someone
  is on) it sends a hidden `echo <mark>;status;echo <mark>` and hides the answer. `status` lists only
  real players (bots are not server clients), by slot; a renamed player (Alien Arena prints nothing
  on a rename) is a leave + join, a map change (slots in `CNCT`) changes nothing. It then writes its
  own lines, read by AMP's regexes:

  ```
  TeamKit : Kevin a rejoint la partie (emplacement 0).      <- UserJoinRegex
  TeamKit : Kevin a quitte la partie (emplacement 0).       <- UserLeaveRegex
  ```
* rewrites **chat lines of real players** (`Marine: hello`, `[TEAM] Marine: hello`, the same format
  as bot taunts) as `[Chat] Marine : hello` / `[Chat equipe] Marine : hello` (`UserChatRegex`); bot
  lines stay untouched;
* prints `TeamKit : serveur Alien Arena pret (port N en UDP).` after the first map load (`AppReadyRegex`);
* on SIGTERM/SIGINT sends `quit`; if the server is still there 20 s after a `quit`, kills it.

AMP stops the instance by typing `quit` (`App.ExitMethod=String`): `==== ShutdownGame ====`, exit
code 0, tested. `Console.FilterMatchRegex=\^[0-9]` strips colour codes in AMP's console; the harmless
start-up lines (`Unknown command "unbindall"`, `Could not exec config.cfg`, terrain lookups) are thrown away.

## Settings exposed in AMP (French UI)

| AMP setting | Game setting | Default |
|---|---|---|
| Port du jeu (Network tab) | `port` | 27910/UDP (game, master list and RCON) |
| Nom du serveur | `hostname` | `^4[^7FR^1] ^5TeamKit ^7- ^2Alien Arena` (in colour: blue/white/red flag, cyan TeamKit, green Alien Arena) |
| Message d'accueil | `motdfile` (centre print on join) | TeamKit welcome + teamkit.fr + Discord, `\|` = new line |
| Joueurs maximum | `maxclients` (`$MaxUsers`, bots included) | 16 (as in `server.cfg`) |
| Spectateurs maximum | `maxspectators` | 4 (game default) |
| Liste publique des serveurs | `sv_public` + `setmaster` | yes |
| Mot de passe pour entrer | `password` (masked) | empty |
| Mot de passe RCON | `rcon_password` (masked) | empty = RCON off |
| Administrateur / Site web affiché | `Admin` / `website` (server info) | `TeamKit` / `https://teamkit.fr` |
| Téléchargement des cartes ajoutées | `allow_download` | on |
| Mode de jeu | `ctf`, `g_tactical`, `g_duel`, `dmflags` 64 | deathmatch (also team DM, CTF, tactical, duel) |
| Carte de départ | `map` | empty = first of the rotation |
| Rotation des cartes | `sv_maplist` | empty = all maps of the mode |
| Durée d'une carte / Score pour finir | `timelimit` / `fraglimit` | 20 min / 20 (`server.cfg`) |
| Échauffement / Protection à l'apparition | `warmuptime` / `g_spawnprotect` | 30 s / 2 s (game defaults) |
| Tir allié | `dmflags` 256 (inverted) | on |
| Votes des joueurs / Vote de la carte suivante | `g_callvote` / `g_mapvote` | on / off |
| Équilibrage des équipes | `g_autobalance` | off |
| Variante d'armes (one at a time, as in the menu) | `instagib`, `rocket_arena`, `insta_rockets`, `excessive`, `classbased`, `all_out_assault` | normal |
| Vampire, Régénération, Changement d'arme rapide, Joueurs plus rapides, Gravité réduite, Joute, Grappin, Anti-campeurs (+ délai) | `vampire`, `regeneration`, `quickweap`, `playerspeed`, `low_grav`, `sv_joustmode`, `grapple`, `anticamp` (+ `camptime`) | off (10 s) |
| Les armes restent / Munitions infinies / Dégâts de chute / Réapparition forcée | `dmflags` 4 / 8192 / 8 (inverted) / 1024 | off / off / on / off |
| Bots | `dmflags` 1048576 (inverted) | on |
| Compléter avec des bots jusqu'à | `sv_botkickthreshold` | 6 players |
| Niveau des bots | `skill` 0–3 | 1 (each bot's own level) |
| Les bots parlent | `dmflags` 262144 (inverted) | off (as in `server.cfg`) |

`dmflags` always includes 16 (instant power-ups) and 2097152 (do not replay the map when a bot wins),
like the official `server.cfg` (`dmflags 2359312`, which is exactly our default). Everything else
(e.g. `sv_tickrate`, `g_randomquad`, `sv_custombots`) goes into `donnees/cor-games/arena/perso.cfg`.

**Bots** join when a real player arrives (one list per map in `data1/botinfo/<map>.tmp`, `team.tmp`
for team modes); with *Compléter avec des bots jusqu'à* = N they fill the game up to N players and
leave one by one as players arrive. When the last player leaves, the bots stay until the next map
change (game behaviour), using a little CPU.

**Added maps:** drop `<map>.bsp` (and its files) into `donnees/cor-games/arena/maps/`; it shows up in
`cartes-disponibles.txt` at the next start and joins the automatic rotation if its prefix fits.

## How a player connects

Listed servers appear in the game (Multiplayer → Join server). Otherwise, in the game console:
`connect IP:port` (`connect IP` when the port is 27910). With a password: `password xxx` first.

## Resources (measured)

| | |
|---|---|
| RAM | ~37 MB idle, ~39 MB with two players and four bots |
| CPU | ~10 % of one core (100 ticks/s, `sv_tickrate`), with or without players |
| Disk | ~1.7 GB (`jeu/`), up to ~3.4 GB briefly during an update to a new version |
| Update | ~1.5 min fresh install (download + build), 0.3 s when up to date |
| Start | ~1 s to ready |

## Not tested

The AMP side itself (Update stages run by AMP, rendering of `reglages-alienarena.txt`, player list
and chat in the panel), the **public listing** (not tried, to avoid announcing a test server; both
master hostnames resolve to IPv4), a Windows or Steam client across the Internet. Everything else
above was run in throwaway `cubecoders/ampbase:debian` containers with two real Alien Arena 7.72.3
clients (built from the same source, software OpenGL under Xvfb).

## Before pushing

```
python verifier.py
```

Must print `Tout est bon.`: JSON, includes, port, complete `Console.*` / `Limits.*` block, new UUIDs
(compared with the other TeamKit templates next to this folder), every AMP setting → model → start
script and back, same choices/bounds/defaults in AMP and the script, Update URLs, LF/ASCII, `bash -n`,
a render → start script → engine command parser round trip on default and tricky values (accents,
quotes, `;`, `\`, `$`, `//`, empty, bad passwords and numbers, every mode, dmflags bits, unknown and
added maps), the bridge on real server lines (joins, bots, chat, team chat, silent rename, RCON
masking, kick, leave, map change, hidden `status` answers) and the console regexes with and without
`FilterMatchRegex`.

## Install in AMP

ADS → Configuration → Instance Deployment → **Configuration Repositories**: add
`hydrocut/AMPTemplates-AlienArena:main`, save, **Fetch latest**. Create Instance →
**Alien Arena: Warriors Of Mars (TeamKit)** → **Update** (must end with
`TeamKit : Alien Arena 7.72.3 installe (20 cartes officielles, 1716 Mo).`) → **Start**.

## Credits

Alien Arena © COR Entertainment, LLC; code GPL-2.0-or-later, game data under COR's distribution
terms. This repository only contains the template; game files come from the official repository,
on the server.

---

## Résumé en français

Template AMP pour le **serveur dédié d'Alien Arena: Warriors Of Mars 7.72.3** (FPS arena libre et
gratuit de COR Entertainment, moteur dérivé de Quake 2). COR ne publie pas de binaire Linux : l'Update
télécharge la dernière version depuis GitHub (1,2 Go) et **compile le serveur seul** dans le conteneur
(environ 1 min 30 en tout ; conteneur obligatoire, paquets gcc, make, libc6-dev, pkg-config,
zlib1g-dev). Un seul port, **27910 en UDP**.

- **Réglages en français dans AMP** : nom, message d'accueil, joueurs et spectateurs max, liste
  publique, mot de passe, RCON (masqués), admin et site affichés, mode (match à mort seul ou en
  équipes, capture du drapeau, tactique, duel), carte de départ et rotation (vide = toutes les cartes
  du mode), durée, score, échauffement, tir allié, votes, variante d'armes (instagib, rocket arena,
  excessive…), mutateurs (vampire, gravité réduite, grappin…), bots (remplissage, niveau, moqueries).
- **Accents** : le jeu n'affiche que l'ASCII ; le script les remplace (é → e) et le dit. Un mot de
  passe avec espace, accent, guillemet, `;` ou `\` empêche le démarrage, avec un message clair.
- Le serveur dédié **exige un terminal** : un petit pont Python lui en donne un, relie la console
  d'AMP (status, kick, map…), suit **les vrais joueurs** (pas les bots) et **leur chat**, masque le
  mot de passe RCON, et arrête proprement par `quit`.
- **Testé en vrai** le 11 oct. 2026 dans des conteneurs jetables, avec deux vrais clients Alien
  Arena : ~37 Mo de RAM, prêt en 1 s. Pas testé : AMP lui-même et l'annonce sur la liste publique.
- Avant de pousser : `python verifier.py` doit répondre « Tout est bon. ».
