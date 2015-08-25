"""
bomb.py - Simple Willie bomb prank game
Copyright 2012, Edward Powell http://embolalia.net
Licensed under the Eiffel Forum License 2.

http://willie.dfbta.net
"""
from __future__ import division
from willie.module import *
from willie.tools import Identifier
from willie import formatting
from random import choice, randrange, sample
from threading import Timer, RLock
import time, random

# code below relies on colors being at least 3 elements long
COLORS = ['Red', 'Light_Green', 'Light_Blue', 'Yellow', 'White', 'Black', 'Purple', 'Orange', 'Pink']
FUSE = 120  # seconds
TIMEOUT = 600
FUSE_TEXT = "%d minute" % (FUSE // 60) if (FUSE % 60) == 0 else ("%d second" % FUSE)
EXPLOSION_TEXT = formatting.color("^!^!^!BOOM!^!^!^", 'red')
EXPLOSION_RANDOM = True if random.randrange(1,100) <= 10 else False # 10% of imminent explosion regardless of wire 
BOMBS = {}
lock = RLock()


@commands('bomb')
@example(".bomb nicky")
@require_chanmsg
def start(bot, trigger):
    """
    Put a bomb in the specified user's pants. They will be kicked if they
     don't guess the right wire fast enough.
    """
    if not trigger.group(3):
        bot.say("Who do you want to bomb?")
        return NOLIMIT
    if bot.db.get_channel_value(trigger.sender, 'bombs_disabled'):
        bot.notice("An admin has disabled bombing in %s." % trigger.sender, trigger.nick)
        return NOLIMIT
    since_last = time_since_bomb(bot, trigger.nick)
    if since_last < TIMEOUT and not trigger.admin:
        bot.notice("You must wait %.0f seconds before you can bomb someone again." % (TIMEOUT - since_last),
                   trigger.nick)
        return
    global BOMBS
    target = Identifier(trigger.group(3))
    target_unbombable = bot.db.get_nick_value(target, 'unbombable')
    if target == bot.nick:
        bot.say("You thought you could trick me into bombing myself?!")
        return NOLIMIT
    if target == trigger.nick:
        bot.say("%s pls. Bomb a friend if you have to!" % trigger.nick)
        return NOLIMIT
    if target.lower() not in bot.privileges[trigger.sender.lower()]:
        bot.say("You can't bomb imaginary people!")
        return NOLIMIT
    if target_unbombable and not trigger.admin:
        bot.say("I'm not allowed to bomb %s, sorry." % target)
        return NOLIMIT
    if bot.db.get_nick_value(trigger.nick, 'unbombable'):
        bot.say("Try again when you're bombable yourself, %s." % trigger.nick)
        return NOLIMIT
    with lock:
        if target.lower() in BOMBS:
            bot.say("I can't fit another bomb in %s's pants!" % target)
            return NOLIMIT
        wires = [COLORS[i] for i in sorted(sample(xrange(len(COLORS)), randrange(3, 5)))]
        num_wires = len(wires)
        wires_list = [formatting.color(str(wire), str(wire)) for wire in wires]
        wires_list = ", ".join(wires_list[:-2] + [" and ".join(wires_list[-2:])]).replace('Light_', '')
        wires = [wire.replace('Light_', '') for wire in wires]
        color = choice(wires)
        bot.say("Hey, %s! I think there's a bomb in your pants. %s timer, %d wires: %s. "
                "Which wire would you like to cut? (respond with %scutwire color)"
                % (target, FUSE_TEXT, num_wires, wires_list, bot.config.core.help_prefix or '.'))
        bot.notice("Hey, don't tell %s, but it's the %s wire." % (target, color), trigger.nick)
        if target_unbombable:
            bot.notice("Just so you know, %s is marked as unbombable." % target, trigger.nick)
        timer = Timer(FUSE, explode, (bot, trigger))
        BOMBS[target.lower()] = (wires, color, timer, target)
        timer.start()
    bombs_planted = bot.db.get_nick_value(trigger.nick, 'bombs_planted') or 0
    bot.db.set_nick_value(trigger.nick, 'bombs_planted', bombs_planted + 1)
    bot.db.set_nick_value(trigger.nick, 'bomb_last_planted', time.time())


@commands('cutwire')
@example(".cutwire red")
@require_chanmsg
def cutwire(bot, trigger):
    """
    Tells willie to cut a wire when you've been bombed.
    """
    global BOMBS
    target = Identifier(trigger.nick)
    with lock:
        if target.lower() != bot.nick.lower() and target.lower() not in BOMBS:
            bot.say("You can't cut a wire until someone bombs you, %s." % target)
            return
        if not trigger.group(3):
            bot.say("You have to choose a wire to cut.")
            return
        # Remove target from bomb list temporarily
        wires, color, timer, orig_target = BOMBS.pop(target.lower())
        wirecut = trigger.group(3)
        if wirecut.lower() in ('all', 'all!') or EXPLOSION_RANDOM:
            timer.cancel()  # defuse timer, execute premature detonation
            
            if EXPLOSION_RANDOM:
                bot.say("Bomb exploded regardless of your wire choice! I'm sorry that you were so unlucky!")
            else:
                bot.say("Cutting ALL the wires! (You should've picked the %s wire.)" % color)

            kickboom(bot, trigger, target)
            alls = bot.db.get_nick_value(orig_target, 'bomb_alls') or 0
            bot.db.set_nick_value(orig_target, 'bomb_alls', alls + 1)
        elif wirecut.capitalize() not in wires:
            bot.say("That wire isn't here, %s! You sure you're picking the right one?" % target)
            # Add the target back onto the bomb list
            BOMBS[target.lower()] = (wires, color, timer, orig_target)
        elif wirecut.capitalize() == color:
            bot.say("You did it, %s! I'll be honest, I thought you were dead. "
                    "But nope, you did it. You picked the right one. Well done." % target)
            timer.cancel()  # defuse bomb
            defuses = bot.db.get_nick_value(orig_target, 'bomb_defuses') or 0
            bot.db.set_nick_value(orig_target, 'bomb_defuses', defuses + 1)
        else:
            timer.cancel()  # defuse timer, execute premature detonation
            bot.say("Nope, wrong wire! Aww, now you've gone and killed yourself. "
                    "Wow. Sorry. (You should've picked the %s wire.)" % color)
            kickboom(bot, trigger, target)
            wrongs = bot.db.get_nick_value(orig_target, 'bomb_wrongs') or 0
            bot.db.set_nick_value(orig_target, 'bomb_wrongs', wrongs + 1)


def explode(bot, trigger):
    target = Identifier(trigger.group(3))
    orig_target = target
    with lock:
        if target.lower() not in BOMBS:  # nick change happened
            for nick in BOMBS.keys():
                if BOMBS[nick][3] == target:
                    target = Identifier(nick)
                    break
        bot.say("%s pls, you could've at least picked one! Now you're dead. You see that? "
                "Guts, all over the place. (You should've picked the %s wire.)" %
                (target, BOMBS[target.lower()][1]))
        kickboom(bot, trigger, target)
        BOMBS.pop(target.lower())
    timeouts = bot.db.get_nick_value(orig_target, 'bomb_timeouts') or 0
    bot.db.set_nick_value(orig_target, 'bomb_timeouts', timeouts + 1)


# helper functions
def kickboom(bot, trigger, target):
    if bot.db.get_channel_value(trigger.sender, 'bomb_kicks') and not bot.db.get_nick_value(target, 'unbombable'):
        kmsg = "KICK %s %s :%s" % (trigger.sender, target, EXPLOSION_TEXT)
        bot.write([kmsg])
    else:
        bot.say("%s is dead! %s" % (target, EXPLOSION_TEXT))


def time_since_bomb(bot, nick):
    now = time.time()
    last = bot.db.get_nick_value(nick, 'bomb_last_planted') or 0
    return abs(last - now)


# Track nick changes
@event('NICK')
@rule('.*')
def bomb_glue(bot, trigger):
    old = trigger.nick
    new = Identifier(trigger)
    with lock:
        if old.lower() in BOMBS:
            BOMBS[new.lower()] = BOMBS.pop(old.lower())
            bot.notice("There's still a bomb in your pants, %s!" % new, new)


@commands('bombstats', 'bombs')
@example(".bombstats")
@example(".bombs myfriend")
def bombstats(bot, trigger):
    """
    Get bomb stats for yourself or another user.
    """
    if not trigger.group(3):
        target = Identifier(trigger.nick)
    else:
        target = Identifier(trigger.group(3))
    wrongs = bot.db.get_nick_value(target, 'bomb_wrongs') or 0
    timeouts = bot.db.get_nick_value(target, 'bomb_timeouts') or 0
    defuses = bot.db.get_nick_value(target, 'bomb_defuses') or 0
    alls = bot.db.get_nick_value(target, 'bomb_alls') or 0
    total = wrongs + timeouts + defuses + alls
    planted = bot.db.get_nick_value(target, 'bombs_planted') or 0
    # short-circuit if user has no stats
    if total == 0:
        msg = "Nobody bombed %s yet!" % target
        if target != trigger.nick:
            msg += " Maybe you should be the first, %s. =3" % trigger.nick
        if planted:
            msg += " Bombs planted: %d" % planted
        bot.say(msg)
        return
    success_rate = defuses / total * 100
    wrongs += alls  # merely a presentation decision
    # grammar shit
    g_wrongs = "time" if wrongs == 1 else "times"
    g_timeouts = "attempt" if timeouts == 1 else "attempts"
    g_defuses = "bomb" if defuses == 1 else "bombs"
    g_alls = "was" if alls == 1 else "were"
    msg = "%s defused %d %s, but failed %d %s and didn't even bother with %d %s." \
          % (target, defuses, g_defuses, wrongs, g_wrongs, timeouts, g_timeouts)
    if alls:
        msg += " (%d of the failures %s from not giving a fuck and cutting ALL the wires!)" % (alls, g_alls)
    msg += " Success rate: %.1f%%" % success_rate
    if planted:
        msg += " Bombs planted: %d" % planted
    bot.say(msg)


@commands('bombstatreset')
@example(".bombstatreset spammer")
@require_owner('Only the bot owner can reset bomb stats')
def statreset(bot, trigger):
    """
    Reset a given user's bomb stats (e.g. after abuse)
    """
    if not trigger.group(3):
        bot.say("Whose bomb stats do you want me to reset?")
        return
    target = Identifier(trigger.group(3))
    keys = ['bomb_wrongs', 'bomb_defuses', 'bomb_timeouts', 'bomb_alls', 'bombs_planted']
    for key in keys:
        bot.db.set_nick_value(target, key, 0)
    bot.say("Bomb stats for %s reset." % target)


@commands('bomboff')
@example(".bomboff")
def exclude(bot, trigger):
    """
    Disable bombing yourself (admins: or another user)
    """
    if not trigger.group(3):
        target = trigger.nick
        time_since = time_since_bomb(bot, target)
        if time_since < TIMEOUT:
            bot.notice(
                "You recently planted a bomb, and must remain bombable for %.0f more seconds." % (TIMEOUT - time_since),
                target)
            return
    else:
        target = Identifier(trigger.group(3))
    if not trigger.admin and target != trigger.nick:
        bot.say("Only bot admins can exclude other users.")
        return
    bot.db.set_nick_value(target, 'unbombable', True)
    bot.say("Marked %s as unbombable." % target)


@commands('bombon')
@example(".bombon")
def unexclude(bot, trigger):
    """
    Re-enable bombing yourself (admins: or another user)
    """
    if not trigger.group(3):
        target = trigger.nick
    else:
        target = Identifier(trigger.group(3))
    if not trigger.admin and target != trigger.nick:
        bot.say("Only bot admins can unexclude other users.")
        return
    bot.db.set_nick_value(target, 'unbombable', False)
    bot.say("Marked %s as bombable again." % target)


@commands('bombkickoff')
@example(".bombkickoff")
@require_privilege(ADMIN, "Only a channel admin or greater can disable bomb kicks.")
@require_chanmsg
def nokick(bot, trigger):
    """
    Allows channel admins and up to disable kicking for bombs in the channel.
    """
    bot.db.set_channel_value(trigger.sender, 'bomb_kicks', False)
    bot.say("Bomb kicks disabled in %s." % trigger.sender)


@commands('bombkickon')
@example(".bombkickon")
@require_privilege(ADMIN, "Only a channel admin or greater can enable bomb kicks.")
@require_chanmsg
def yeskick(bot, trigger):
    """
    Allows channel admins and up to (re-)enable kicking for bombs in the channel.
    """
    bot.db.set_channel_value(trigger.sender, 'bomb_kicks', True)
    bot.say("Bomb kicks enabled in %s." % trigger.sender)


@commands('bombsoff')
@example(".bombsoff")
@require_privilege(ADMIN, "Only a channel admin or greater can disable bombing in this channel.")
@require_chanmsg
def bombnazi(bot, trigger):
    """
    Allows channel admins and up to disable bombing entirely in the current channel.
    """
    bot.db.set_channel_value(trigger.sender, 'bombs_disabled', True)
    bot.say("Bombs disabled in %s." % trigger.sender)


@commands('bombson')
@example(".bombson")
@require_privilege(ADMIN, "Only a channel admin or greater can enable bombing in this channel.")
@require_chanmsg
def bomboprah(bot, trigger):
    """
    Allows channel admins and up to (re-)enable bombing in the current channel.
    """
    bot.db.set_channel_value(trigger.sender, 'bombs_disabled', False)
    bot.say("Bombs enabled in %s." % trigger.sender)


@commands('bombnickmerge')
@example(".bombnickmerge newbie into old_friend")
@require_owner("Only the bot owner can merge users.")
def is_really(bot, trigger):
    """
    Merge the two nicks, keeping the stats for the second one.
    """
    duplicate = trigger.group(3) or None
    primary = trigger.group(5) or None
    if not primary or not duplicate or trigger.group(4).lower() != 'into':
        bot.reply("I want to be sure there are no mistakes here. "
                  "Please specify nicks to merge as: <duplicate> into <primary>")
        return
    duplicate = Identifier(duplicate)
    primary = Identifier(primary)
    newstats = dict()
    for stat in ('bomb_wrongs', 'bomb_timeouts', 'bomb_defuses', 'bomb_alls', 'bombs_planted'):
        dupval = bot.db.get_nick_value(duplicate, stat) or 0
        prival = bot.db.get_nick_value(primary, stat) or 0
        newstats[stat] = dupval + prival
    for stat in newstats:
        bot.db.set_nick_value(primary, stat, newstats[stat])
        bot.db.set_nick_value(duplicate, stat, 0)  # because willie < 5.4.1 doesn't merge properly
    bot.db.merge_nick_groups(primary, duplicate)
    bot.say("Merged %s into %s." % (duplicate, primary))
