#!/bin/bash
# lancer-alienarena.sh - pose par le template AMP TeamKit (recree a chaque Update).
#
#   lancer-alienarena.sh <port> <joueurs max>
#
# 1. lit les reglages ecrits par AMP (reglages-alienarena.txt, une ligne cle=valeur, valeurs
#    brutes), les controle, rend les textes lisibles par le jeu (il n'affiche que l'ASCII),
#    puis ecrit donnees/cor-games/arena/amp-teamkit.cfg et amp-motd.txt ;
# 2. lance le serveur dedie (jeu/alienarena-ded) DANS UN PSEUDO-TERMINAL : il quitte tout
#    seul, sans un mot, si son entree ou sa sortie n'est pas un terminal (main() de
#    source/unix/sys_unix.c), or AMP lui donne des tuyaux. Le petit programme "pont"
#    ci-dessous fait le lien : console d'AMP -> serveur, serveur -> console d'AMP,
#    liste des joueurs (via la commande status, en cache) et arret propre par quit.
cd "$(dirname "$0")" || exit 1
export LANG=C.UTF-8 LC_ALL=C.UTF-8
ICI="$PWD"
JEU="$ICI/jeu"
BIN="$JEU/alienarena-ded"
DONNEES="$ICI/donnees"
PORT="$1"
JOUEURS="$2"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
  echo "ERREUR : port invalide : '$PORT'."
  exit 1
fi
if [ ! -x "$BIN" ] || [ ! -f "$JEU/data1/pics/colormap.pcx" ]; then
  echo "ERREUR : Alien Arena n'est pas installe (jeu/alienarena-ded absent) : lance Update."
  exit 1
fi
if [ ! -f reglages-alienarena.txt ]; then
  echo "ERREUR : reglages-alienarena.txt absent. AMP l'ecrit au demarrage a partir de AMP_reglages-alienarena.txt : lance Update."
  exit 1
fi
# Le jeu cree cor-games/ dans XDG_DATA_HOME mais pas XDG_DATA_HOME lui-meme.
mkdir -p "$DONNEES/cor-games/arena" || exit 1

python3 -I - "$ICI" "$JOUEURS" <<'PY'
import glob, io, os, re, sys, textwrap, unicodedata

ICI, JOUEURS = sys.argv[1], sys.argv[2]
JEU = os.path.join(ICI, 'jeu')
PERSO = os.path.join(ICI, 'donnees', 'cor-games', 'arena')
erreurs = []


def dire(texte):
    print('TeamKit : ' + texte, flush=True)


# 1. reglages ecrits par AMP (cle=valeur, valeur brute jusqu'a la fin de la ligne)
R = {}
with io.open(os.path.join(ICI, 'reglages-alienarena.txt'), encoding='utf-8', errors='replace') as f:
    for ligne in f:
        ligne = ligne.rstrip('\r\n')
        if '=' in ligne and not ligne.startswith('#'):
            k, v = ligne.split('=', 1)
            R[k.strip()] = v
R['maxclients'] = JOUEURS

# 2. textes : le jeu n'affiche que l'ASCII (police : octet & 0x7F, ref_gl/r_ttf.c) ;
#    " ; et \ sont interdits dans les infostrings (nom du serveur, admin, site).
REMPLACE = {'\u0153': 'oe', '\u0152': 'OE', '\u00e6': 'ae', '\u00c6': 'AE', '\u00df': 'ss',
            '\u2014': '-', '\u2013': '-', '\u2012': '-', '\u2212': '-', '\u00b7': '-', '\u2022': '-',
            '\u2019': "'", '\u2018': "'", '\u00ab': "'", '\u00bb': "'", '\u201c': "'", '\u201d': "'",
            '\u2026': '...', '\u20ac': ' euros', '\u00a0': ' ', '\u202f': ' ', '\u2009': ' ',
            '"': "'", ';': ',', '\\': '/'}


def texte_jeu(v):
    # guillemets francais avec leurs espaces : << mot >> devient 'mot'
    s = re.sub(chr(0xab) + r'[ ' + chr(0xa0) + chr(0x202f) + r']*', "'", v)
    s = re.sub(r'[ ' + chr(0xa0) + chr(0x202f) + r']*' + chr(0xbb), "'", s)
    s = ''.join(REMPLACE.get(c, c) for c in s)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = ''.join(c if 32 <= ord(c) < 127 else '?' for c in s)
    return re.sub(r' {2,}', ' ', s).strip()


def texte(cle, maxi):
    brut = R.get(cle, '')
    propre = texte_jeu(brut)
    if propre != brut.strip():
        dire('%s : accents et caracteres speciaux remplaces (le jeu ne sait pas les afficher) -> %s' % (cle, propre))
    if len(propre) > maxi:
        propre = propre[:maxi].rstrip()
        dire('%s : trop long, coupe a %d caracteres -> %s' % (cle, maxi, propre))
    return propre


def nombre(cle, defaut, mini, maxi):
    v = R.get(cle, '').strip()
    if v == '':
        return defaut
    if not re.fullmatch(r'-?\d+', v) or not (mini <= int(v) <= maxi):
        erreurs.append('%s = %r : un nombre entier entre %d et %d.' % (cle, v, mini, maxi))
        return defaut
    return int(v)


def choix(cle, defaut, permis):
    v = R.get(cle, '').strip() or defaut
    if v not in permis:
        erreurs.append('%s = %r : valeurs possibles %s.' % (cle, v, ', '.join(permis)))
        return defaut
    return v


def case(cle, defaut):
    # case a cocher : AMP ecrit la valeur de EnumValues (1/0) ; True/False acceptes aussi
    v = R.get(cle, '').strip()
    R[cle] = {'true': '1', 'false': '0'}.get(v.lower(), v)
    return choix(cle, defaut, ['0', '1']) == '1'


def mot_de_passe(cle, nom, interdit_none):
    v = R.get(cle, '')
    if v and not re.fullmatch(r'[!#-:<-\[\]-~]{1,63}', v):
        erreurs.append('%s : 63 caracteres au plus, sans espace, accent, guillemet, point-virgule ni '
                       'antislash (le jeu ne les accepte pas dans un mot de passe).' % nom)
        return ''
    if interdit_none and v == 'none':
        erreurs.append('%s : "none" veut dire "pas de mot de passe" pour le jeu : choisis-en un autre, ou laisse vide.' % nom)
        return ''
    return v


nom = texte('hostname', 63) or 'TeamKit - Alien Arena'
admin = texte('admin', 63)
site = texte('website', 63)
joueurs = nombre('maxclients', 16, 2, 32)
spectateurs = nombre('maxspectators', 4, 0, 32)
public = choix('sv_public', '1', ['0', '1'])
entree = mot_de_passe('password', 'Mot de passe pour entrer', True)
rcon = mot_de_passe('rcon_password', 'Mot de passe RCON', False)
telechargement = case('allow_download', '1')
mode = choix('mode', 'dm', ['dm', 'tdm', 'ctf', 'tac', 'duel'])
temps = nombre('timelimit', 20, 0, 999)
score = nombre('fraglimit', 20, 0, 9999)
echauffement = nombre('warmuptime', 30, 0, 300)
protection = nombre('g_spawnprotect', 2, 0, 10)
ARMES = ['instagib', 'rocket_arena', 'insta_rockets', 'excessive', 'classbased', 'all_out_assault']
armes = choix('armes', 'normal', ['normal'] + ARMES)
MUTATEURS = ['vampire', 'regeneration', 'quickweap', 'playerspeed', 'low_grav', 'sv_joustmode', 'grapple', 'anticamp']
mutateurs = {m: case(m, '0') for m in MUTATEURS}
campeur = nombre('camptime', 10, 1, 120)
tir_allie = case('tir_allie', '1')
armes_restent = case('armes_restent', '0')
munitions = case('munitions_infinies', '0')
chute = case('degats_chute', '1')
reapparition = case('reapparition_forcee', '0')
votes = case('g_callvote', '1')
vote_carte = case('g_mapvote', '0')
equilibrage = case('g_autobalance', '0')
bots = case('bots', '1')
remplissage = nombre('sv_botkickthreshold', 6, 0, 32)
niveau = choix('skill', '1', ['0', '1', '2', '3'])
bots_parlent = case('bots_parlent', '0')

# Message d'accueil : | = retour a la ligne ; lignes de 40 caracteres au plus.
accueil, change = [], False
for morceau in R.get('motd', '').split('|'):
    propre = texte_jeu(morceau)
    change = change or propre != re.sub(r' {2,}', ' ', morceau.strip())
    accueil += textwrap.wrap(propre, 40) if propre else []
if change:
    dire('motd : accents et caracteres speciaux remplaces (le jeu ne sait pas les afficher).')
motd = '\n'.join(accueil)
if len(motd) > 500:
    motd = motd[:500]
    dire('motd : trop long, coupe a 500 caracteres.')

# 3. dmflags (q_shared.h) : bonus instantanes (16) et "ne pas rejouer la carte si un bot
#    gagne" (2097152) comme dans le server.cfg officiel, puis les reglages d'AMP.
dmflags = 16 | 2097152
dmflags |= 64 if mode == 'tdm' else 0                 # DF_SKINTEAMS, match a mort en equipes
dmflags |= 0 if tir_allie else 256                    # DF_NO_FRIENDLY_FIRE
dmflags |= 4 if armes_restent else 0                  # DF_WEAPONS_STAY
dmflags |= 8192 if munitions else 0                   # DF_INFINITE_AMMO
dmflags |= 0 if chute else 8                          # DF_NO_FALLING
dmflags |= 1024 if reapparition else 0                # DF_FORCE_RESPAWN
dmflags |= 0 if bots else 1048576                     # DF_BOTS (bots desactives)
dmflags |= 0 if bots_parlent else 262144              # DF_BOTCHAT (bots muets)

# 4. cartes installees : officielles (jeu/data1/maps), essais des developpeurs
#    (jeu/arena/maps) et ajoutees (donnees/cor-games/arena/maps ou data1/maps)
cartes = {}
for dossier in (os.path.join(JEU, 'data1', 'maps'), os.path.join(JEU, 'arena', 'maps'),
                os.path.join(PERSO, 'maps'), os.path.join(ICI, 'donnees', 'cor-games', 'data1', 'maps')):
    for bsp in sorted(glob.glob(os.path.join(dossier, '*.bsp'))):
        c = os.path.basename(bsp)[:-4]
        if re.fullmatch(r'[A-Za-z0-9_.+-]{1,60}', c):
            cartes.setdefault(c.lower(), c)
if not cartes:
    erreurs.append('aucune carte trouvee dans jeu/data1/maps : lance Update.')
with io.open(os.path.join(ICI, 'cartes-disponibles.txt'), 'w', encoding='utf-8', newline='\n') as f:
    f.write('# Cartes trouvees au dernier demarrage, a recopier dans les reglages d\'AMP.\n'
            '# dm- : match a mort (seul, en equipes, duel) ; ctf- : drapeau ; tac- : tactique.\n')
    f.write('\n'.join(cartes[c] for c in sorted(cartes)) + '\n')

PREFIXES = {'dm': ('dm-', 'tourney-'), 'tdm': ('dm-', 'tourney-'), 'duel': ('dm-', 'tourney-'),
            'ctf': ('ctf-',), 'tac': ('tac-',)}[mode]
NOMS_MODE = {'dm': 'match a mort', 'tdm': 'match a mort en equipes', 'duel': 'duel',
             'ctf': 'capture du drapeau', 'tac': 'tactique'}
# Rotation automatique : l'ordre de la liste officielle (jeu/arena/maps.lst, celle du menu
# du jeu) pour les cartes qu'elle cite, puis les autres par ordre alphabetique.
officielles = []
try:
    with io.open(os.path.join(JEU, 'arena', 'maps.lst'), encoding='latin-1') as f:
        officielles = [l.split()[0].lower() for l in f if l.split()]
except OSError:
    pass
ordre = [c for c in officielles if c in cartes] + sorted(c for c in cartes if c not in officielles)
du_mode = []
for c in ordre:
    if c.startswith(PREFIXES) and cartes[c] not in du_mode:
        du_mode.append(cartes[c])
rotation, inconnues = [], []
for c in re.split(r'[\s,;]+', R.get('sv_maplist', '')):
    if not c:
        continue
    if c.lower() in cartes:
        if cartes[c.lower()] not in rotation:
            rotation.append(cartes[c.lower()])
    else:
        inconnues.append(c)
if inconnues:
    dire('ATTENTION, cartes introuvables retirees de la rotation : %s (liste dans cartes-disponibles.txt).'
         % ', '.join(inconnues))
if not rotation:
    if R.get('sv_maplist', '').strip():
        dire('ATTENTION, aucune carte de la rotation n\'existe : toutes les cartes du mode a la place.')
    rotation = du_mode
if not rotation and cartes:
    erreurs.append('aucune carte %s installee pour le mode %s.' % ('/'.join(PREFIXES), NOMS_MODE[mode]))
autres = [c for c in rotation if not c.lower().startswith(PREFIXES)]
if autres:
    dire('ATTENTION, cartes qui ne sont pas faites pour le mode %s : %s.' % (NOMS_MODE[mode], ', '.join(autres)))
liste = ' '.join(rotation)
if len(liste) > 900:
    erreurs.append('rotation trop longue (%d caracteres, 900 au plus) : enleve des cartes.' % len(liste))

depart = R.get('map', '').strip()
if depart and depart.lower() in cartes:
    depart = cartes[depart.lower()]
else:
    if depart:
        dire('ATTENTION, carte de depart %r introuvable : %s a la place.' % (depart, rotation[0] if rotation else '?'))
    depart = rotation[0] if rotation else ''

if erreurs:
    for e in erreurs:
        print('ERREUR : ' + e, flush=True)
    print("Corrige ce reglage dans l'onglet Configuration d'AMP, puis relance.", flush=True)
    sys.exit(1)

# 5. donnees/cor-games/arena/amp-teamkit.cfg (lu par +exec ; les valeurs n'ont ni " ni ;)
L = ['// amp-teamkit.cfg - ECRIT PAR lancer-alienarena.sh a chaque demarrage, a partir des',
     "// reglages d'AMP. Ne le modifie pas : mets tes reglages en plus dans perso.cfg.",
     'set hostname "%s"' % nom,
     'set Admin "%s" s' % admin,
     'set website "%s" s' % site,
     'set maxclients "%d"' % joueurs,
     'set maxspectators "%d"' % spectateurs,
     'set password "%s"' % entree,
     'set rcon_password "%s"' % rcon,
     'set sv_public "%s"' % public,
     'set allow_download "%d"' % telechargement,
     'set deathmatch "1"',
     'set ctf "%d"' % (mode == 'ctf'),
     'set g_tactical "%d"' % (mode == 'tac'),
     'set g_duel "%d"' % (mode == 'duel'),
     'set dmflags "%d"' % dmflags,
     'set timelimit "%d"' % temps,
     'set fraglimit "%d"' % score,
     'set warmuptime "%d"' % echauffement,
     'set g_spawnprotect "%d"' % protection]
L += ['set %s "%d"' % (a, armes == a) for a in ARMES]
L += ['set %s "%d"' % (m, mutateurs[m]) for m in MUTATEURS]
L += ['set camptime "%d"' % campeur,
      'set g_callvote "%d"' % votes,
      'set g_mapvote "%d"' % vote_carte,
      'set g_autobalance "%d"' % equilibrage,
      'set sv_botkickthreshold "%d"' % remplissage,
      'set skill "%s"' % niveau,
      'set sv_maplist "%s"' % liste,
      'set motdfile "amp-motd.txt"']
if public == '1':
    L.append('// Serveurs maitres officiels (server.cfg du jeu, qcommon.h : DEFAULT_MASTER_1/2).')
    L.append('setmaster master.alienarena.org master2.alienarena.org')
L += ['exec perso.cfg', 'map %s' % depart]
with io.open(os.path.join(PERSO, 'amp-teamkit.cfg'), 'w', encoding='ascii', newline='\n') as f:
    f.write('\n'.join(L) + '\n')
with io.open(os.path.join(PERSO, 'amp-motd.txt'), 'w', encoding='ascii', newline='\n') as f:
    f.write(motd + ('\n' if motd else ''))

perso = os.path.join(PERSO, 'perso.cfg')
if not os.path.isfile(perso):
    with io.open(perso, 'w', encoding='ascii', newline='\n') as f:
        f.write('// perso.cfg - tes reglages Alien Arena en plus, un par ligne (voir CVAR.md du jeu).\n'
                '// Lu a chaque demarrage APRES les reglages d\'AMP : il peut donc les remplacer.\n'
                '// Le template ne l\'ecrase jamais. Exemples :\n'
                '// set sv_tickrate "100"\n// set g_randomquad "1"\n')

dire('%s, mode %s%s, carte %s, rotation de %d cartes, %d joueurs max, %s, RCON %s.' % (
    'annonce sur la liste publique' if public == '1' else 'non liste (connexion par IP)',
    NOMS_MODE[mode], '' if armes == 'normal' else ' (' + armes + ')', depart, len(rotation), joueurs,
    'mot de passe pour entrer' if entree else 'ouvert a tous',
    'actif' if rcon else 'desactive (mot de passe vide)'))
PY
[ $? = 0 ] || exit 1

# Le pont : pseudo-terminal pour le serveur, console d'AMP reliee, liste des joueurs.
PONT='
import os, re, select, signal, sys, time

COULEUR = re.compile(r"\^[^^]")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ETAT = re.compile(r"^ *(\d+) +(\S+) +(\S+) (.*?) +(-?\d+) (\S+) +(-?\d+)$")
EVENEMENT = re.compile(r"^.+ (entered the game|disconnected|timed out|was kicked|connected)$|^Was a duplicate, changing name to ")
RCON = re.compile(r"^(Bad rcon|Rcon) from \S+:$")


def nom_jeu(brut):
    # meme traitement que ValidatePlayerName (game/q_shared.c) : le nom tel que le chat l ecrit
    s = "".join(c if 33 <= ord(c) < 127 else " " for c in brut)
    sortie, glyphes, i = "", 0, 0
    while i < len(s) and glyphes < 15 and len(sortie) < 31:
        if s[i] == "^" and i + 1 < len(s) and s[i + 1] != "^":
            if len(sortie) >= 28:
                break
            sortie += s[i:i + 2]
            i += 2
        else:
            sortie += s[i]
            glyphes += 1
            i += 1
    return sortie


def propre(nom):
    return COULEUR.sub("", nom).strip() or "sans_nom"


class Pont:
    """Relie le serveur (pseudo-terminal) et AMP. ecrire_jeu(octets) parle au serveur,
    sortir(texte) ecrit une ligne dans la console d AMP."""

    def __init__(self, port, ecrire_jeu, sortir, marque):
        self.port, self.ecrire_jeu, self.sortir, self.marque = port, ecrire_jeu, sortir, marque
        self.presents = {}          # emplacement -> nom tel que le jeu l ecrit (chat)
        self.en_cache = None        # lignes de la commande status cachee, ou None
        self.cache_depuis = 0.0
        self.statut_a = 0.0         # heure de la prochaine commande status (0 = aucune)
        self.dernier_statut = 0.0
        self.init_vue = False
        self.pret = False
        self.rcon_suit = False
        self.arret = 0.0
        self.saisie = b""

    def dire(self, texte):
        self.sortir("TeamKit : " + texte)

    def demander_statut(self, dans, maintenant):
        quand = maintenant + dans
        if not self.statut_a or quand < self.statut_a:
            self.statut_a = quand

    def appliquer_statut(self, lignes):
        vus = {}
        for l in lignes:
            m = ETAT.match(l)
            if not m or m.group(3) == "ZMBI":
                continue
            n = m.group(1)
            if m.group(3) == "CNCT":
                if n in self.presents:
                    vus[n] = self.presents[n]      # changement de carte : on garde
                continue                           # pas encore entre dans la partie
            vus[n] = nom_jeu(m.group(4))
        for n in sorted(set(self.presents) | set(vus), key=int):
            avant, apres = self.presents.get(n), vus.get(n)
            if avant is not None and avant != apres:
                self.dire("%s a quitte la partie (emplacement %s)." % (propre(avant), n))
            if apres is not None and avant != apres:
                self.dire("%s a rejoint la partie (emplacement %s)." % (propre(apres), n))
        self.presents = vus

    def ligne_du_jeu(self, l, maintenant):
        l = ANSI.sub("", l).replace("\r", "")
        if self.en_cache is not None:
            if l.strip() == self.marque + "-fin":
                lignes, self.en_cache = self.en_cache, None
                self.appliquer_statut(lignes)
            else:
                self.en_cache.append(l)
            return
        if l.strip() == self.marque + "-debut":
            self.en_cache, self.cache_depuis = [], maintenant
            return
        if self.rcon_suit and l.startswith("rcon "):
            l = re.sub(r"^rcon +\S+", "rcon ***", l)
        self.rcon_suit = bool(RCON.match(l))
        for prefixe, genre in (("[TEAM] ", "Chat equipe"), ("", "Chat")):
            for nom in sorted(set(self.presents.values()), key=len, reverse=True):
                debut = prefixe + nom + ": "
                if l.startswith(debut):
                    self.sortir("[%s] %s : %s" % (genre, propre(nom), l[len(debut):]))
                    return
        self.sortir(l)
        if l == "------- Server Initialization -------":
            self.init_vue = True
        elif self.init_vue and not self.pret and re.fullmatch(r"-{20,}", l):
            self.pret = True
            self.dire("serveur Alien Arena pret (port %s en UDP)." % self.port)
        if EVENEMENT.match(l) and "(bot)" not in l:
            self.demander_statut(0.5, maintenant)

    def commande_amp(self, donnees, maintenant):
        self.saisie += donnees.replace(b"\r", b"")
        while b"\n" in self.saisie:
            commande, self.saisie = self.saisie.split(b"\n", 1)
            commande = commande.strip()[:250]       # le serveur lit 256 octets au plus par ligne
            if commande:
                if commande.lower() == b"quit":
                    self.arret = self.arret or maintenant + 20
                self.ecrire_jeu(commande + b"\n")

    def tic(self, maintenant):
        if self.en_cache is not None and maintenant - self.cache_depuis > 5:
            for l in self.en_cache:                 # reponse incomplete : on rend les lignes
                self.sortir(l)
            self.en_cache = None
        if self.presents and maintenant - self.dernier_statut > 30:
            self.demander_statut(0, maintenant)     # un nom peut changer sans rien afficher
        if self.statut_a and maintenant >= self.statut_a and self.en_cache is None \
                and self.pret and not self.arret:
            self.statut_a, self.dernier_statut = 0.0, maintenant
            self.ecrire_jeu(("echo %s-debut;status;echo %s-fin\n" % (self.marque, self.marque)).encode())


def principal():
    import pty, subprocess, termios
    port, jeu, commande = sys.argv[1], sys.argv[2], sys.argv[3:]
    maitre, esclave = pty.openpty()
    reglage = termios.tcgetattr(esclave)
    reglage[1] &= ~termios.OPOST                    # pas de \r ajoute en sortie
    reglage[3] &= ~(termios.ECHO | termios.ECHONL)  # les commandes ne reviennent pas en echo
    termios.tcsetattr(esclave, termios.TCSANOW, reglage)
    serveur = subprocess.Popen(commande, cwd=jeu, stdin=esclave, stdout=esclave, stderr=esclave,
                               start_new_session=True, close_fds=True)
    os.close(esclave)

    def ecrire_jeu(octets):
        try:
            os.write(maitre, octets)
        except OSError:
            pass

    def sortir(texte):
        os.write(1, (texte + "\n").encode("utf-8", "replace"))

    pont = Pont(port, ecrire_jeu, sortir, "teamkit-statut-%d" % os.getpid())

    def demander_arret(signum, frame):
        if not pont.arret:
            pont.arret = time.time() + 20
            ecrire_jeu(b"quit\n")

    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, demander_arret)
    tampon, entree_ouverte = b"", True
    while True:
        maintenant = time.time()
        if pont.arret and maintenant > pont.arret and serveur.poll() is None:
            pont.dire("le serveur ne s est pas arrete apres quit : arret force.")
            os.killpg(serveur.pid, signal.SIGKILL)
        pont.tic(maintenant)
        try:
            prets = select.select([maitre] + ([0] if entree_ouverte else []), [], [], 0.25)[0]
        except InterruptedError:
            continue
        if maitre in prets:
            try:
                donnees = os.read(maitre, 65536)
            except OSError:
                donnees = b""
            if not donnees:
                break
            tampon += donnees
            while b"\n" in tampon:
                brut, tampon = tampon.split(b"\n", 1)
                pont.ligne_du_jeu(brut.decode("utf-8", "replace"), time.time())
        if 0 in prets:
            donnees = os.read(0, 4096)
            if not donnees:
                entree_ouverte, donnees = False, b"\n"
            pont.commande_amp(donnees, time.time())
    if tampon:
        pont.ligne_du_jeu(tampon.decode("utf-8", "replace"), time.time())
    code = serveur.wait()
    sys.exit(code if code >= 0 else 128 - code)


if __name__ == "__main__":
    principal()
'

# Utilise seulement par verifier.py : s'arrete avant de lancer le jeu.
[ -n "$TK_ESSAI" ] && { echo "TK_ESSAI pret"; exit 0; }

# exec : le pont remplace ce script et garde l'entree d'AMP (console, "quit" d'arret).
# sys_ansicolor 0 : pas de couleurs ANSI, logfile 0 : AMP garde deja la console.
export XDG_DATA_HOME="$DONNEES"
exec python3 -I -u -c "$PONT" "$PORT" "$JEU" "$BIN" +set sys_ansicolor 0 +set logfile 0 \
  +set port "$PORT" +exec amp-teamkit.cfg
