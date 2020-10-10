import xml.etree.ElementTree as ET
import glob, os, sqlite3, os, sys, re, json
import protobuf.usagestatsservice_pb2 as usagestatsservice_pb2
from enum import IntEnum


class EventType(IntEnum):
    NONE = 0
    MOVE_TO_FOREGROUND = 1
    MOVE_TO_BACKGROUND = 2
    END_OF_DAY = 3
    CONTINUE_PREVIOUS_DAY = 4
    CONFIGURATION_CHANGE = 5
    SYSTEM_INTERACTION = 6
    USER_INTERACTION = 7
    SHORTCUT_INVOCATION = 8
    CHOOSER_ACTION = 9
    NOTIFICATION_SEEN = 10
    STANDBY_BUCKET_CHANGED = 11
    NOTIFICATION_INTERRUPTION = 12
    SLICE_PINNED_PRIV = 13
    SLICE_PINNED = 14
    SCREEN_INTERACTIVE = 15
    SCREEN_NON_INTERACTIVE = 16
    KEYGUARD_SHOWN = 17
    KEYGUARD_HIDDEN = 18

    def __str__(self):
        return self.name  # This returns 'KNOWN' instead of 'EventType.KNOWN'


class EventFlag(IntEnum):
    FLAG_IS_PACKAGE_INSTANT_APP = 1

    def __str__(self):
        return self.name


def read_usage_stats_pb_file(input_path):
    """Opens file, reads usagestats protobuf and returns IntervalStatsProto object"""
    stats = usagestatsservice_pb2.IntervalStatsProto()

    with open(input_path, 'rb') as f:
        stats.ParseFromString(f.read())
    return stats


def add_entries_to_db(stat_frequency, db):
    cursor = db.cursor()
    # packages
    for usagestat in stat_frequency.packages:
        finalt = ''
        if usagestat.HasField('last_time_active_ms'):
            finalt = usagestat.last_time_active_ms
            if finalt < 0:
                finalt = abs(finalt)
            else:
                finalt += file_name_int
        tac = ''
        if usagestat.HasField('total_time_active_ms'):
            tac = abs(usagestat.total_time_active_ms)
        pkg = stat_frequency.stringpool.strings[usagestat.package_index - 1]
        alc = ''
        if usagestat.HasField('app_launch_count'):
            alc = abs(usagestat.app_launch_count)

        datainsert = ('packages', finalt, tac, '', '', '', alc, pkg, '', '', sourced, '')
        # print(datainsert)
        cursor.execute(
            'INSERT INTO data (usage_type, lastime, timeactive, last_time_service_used, last_time_visible, total_time_visible, '
            'app_launch_count, package, types, classs, source, fullatt)  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', datainsert)
    # configurations
    for conf in stat_frequency.configurations:
        usagetype = 'configurations'
        finalt = ''
        if usagestat.HasField('last_time_active_ms'):
            finalt = usagestat.last_time_active_ms
            if finalt < 0:
                finalt = abs(finalt)
            else:
                finalt += file_name_int
        tac = ''
        if usagestat.HasField('total_time_active_ms'):
            tac = abs(usagestat.total_time_active_ms)
        fullatti_str = str(conf.config)
        datainsert = (usagetype, finalt, tac, '', '', '', '', '', '', '', stat_frequency, fullatti_str)
        # print(datainsert)
        cursor.execute(
            'INSERT INTO data (usage_type, lastime, timeactive, last_time_service_used, last_time_visible, total_time_visible, '
            'app_launch_count, package, types, classs, source, fullatt)  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', datainsert)
    # event-log
    usagetype = 'event-log'
    for event in stat_frequency.event_log:
        pkg = ''
        classy = ''
        tipes = ''
        finalt = ''
        if event.HasField('time_ms'):
            finalt = event.time_ms
            if finalt < 0:
                finalt = abs(finalt)
            else:
                finalt += file_name_int
        if event.HasField('package_index'):
            pkg = stat_frequency.stringpool.strings[event.package_index - 1]
        if event.HasField('class_index'):
            classy = stat_frequency.stringpool.strings[event.class_index - 1]
        if event.HasField('type'):
            tipes = str(EventType(event.type)) if event.type <= 18 else str(event.type)
        datainsert = (usagetype, finalt, '', '', '', '', '', pkg, tipes, classy, sourced, '')
        cursor.execute(
            'INSERT INTO data (usage_type, lastime, timeactive, last_time_service_used, last_time_visible, total_time_visible, '
            'app_launch_count, package, types, classs, source, fullatt)  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', datainsert)

    db.commit()


def create_table():
    processed = 0

    # Create sqlite databases
    db = sqlite3.connect('usagestats.db')
    cursor = db.cursor()

    # Create table usagedata.

    cursor.execute('''

           CREATE TABLE data(usage_type TEXT, lastime INTEGER, timeactive INTEGER,
                             last_time_service_used INTEGER, last_time_visible INTEGER, total_time_visible INTEGER,
                             app_launch_count INTEGER,
                             package TEXT, types TEXT, classs TEXT,
                             source TEXT, fullatt TEXT)

       ''')

    db.commit()
    return db, cursor


def parse_file_with_protobuf(path_to_file, db):
    """
    Try to parse the usagestats file with a protobuf.
    Credits for protobuf support goes to Yogesh Khatri, see the readme for the blogpost
    :param path_to_file: The path to the file (including the file) to be parsed.
    :param db: The database to write the results to
    :return:
    """
    stats = None
    # Perhaps an Android Q protobuf file
    try:
        stats = read_usage_stats_pb_file(path_to_file)

    except:
        print('Parse error - Non XML and Non Protobuf file? at: ' + path_to_file)

    add_entries_to_db(stats, db)


def calc_last_time_active(xml_element, filename):
    """
    Calculate the absolute time (in EPOCH) when an event was active for the last time.
    :param xml_element: The element containing an lastTimeActive attribute
    :param filename: A filename where the name contains digits only, representing the creation time in EPOCH.
    :return: The EPOCH representation of the time an event was active for the last time.
    """
    if 'lastTimeActive' in xml_element.keys():
        relative_last_time_active = int(xml_element.attrib['lastTimeActive'])

        # Some events show the last_time_active as EPOCH already, which is indicated by starting with a minus sign
        if relative_last_time_active < 0:
            last_time_active = abs(relative_last_time_active)

        # Otherwise we need to add the filename (which is the start time in EPOCH)
        # to the relative time (represented in ms)
        else:
            last_time_active = int(filename) + relative_last_time_active
        return last_time_active

    else:
        return ''


def parse_sub_elements(frequency, xml_element, filename, db):
    """
    Parse all childs of the <packages> element.
    Example how a child element looks like:
        <package lastTimeActive="-1589192784125"  package="com.samsung.android.provider.filterprovider"
            timeActive="0" lastEvent="0" />

    And store them in the database
    :param frequency: The frequency of usagestats record (daily, weekly, monthly or yearly)
    :param xml_element: the element <packages> containing all its childs
    :param filename: The filename being parsed, already checked if it only contains numbers.
                    This represents an EPOCH timestamp
    :param db: handle to a database
    :return:
    """
    for child in xml_element:
        all_attributes = json.dumps(child.attrib)
        usage_type = xml_element.tag
        # If the attribute exists in this xml element, fetch its value. Otherwise set to ''
        last_active_time = calc_last_time_active(child, filename)
        package = child.attrib.get('package', '')
        time_active = child.attrib.get('timeActive', '')
        app_launch = child.attrib.get('appLaunchCount', '')
        type_class = child.attrib.get('class', '')
        type_type = child.attrib.get('type', '')

        values = (usage_type, last_active_time, time_active, '', '', '', app_launch, package,
                  type_type, type_class, frequency, all_attributes)
        cursor = db.cursor()
        cursor.execute(
            'INSERT INTO data (usage_type, lastime, timeactive, last_time_service_used, last_time_visible, total_time_visible, '
            'app_launch_count, package, types, classs, source, fullatt)  VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            values)
        db.commit()


def usagestats_parse(dirpath):
    """
    Parse every usagestat file, based on an input directory
    :param dirpath: string to file to parse
    :return:
    """
    # Create database
    # TODO: change to an easier format, probably json.
    db, cursor = create_table()

    # Some vars for logging
    processed = 0
    err = 0

    # Iterate through the /usagestats/ directory and fetch all files
    for root, dirnames, filenames in os.walk(dirpath, topdown=True, onerror=None, followlinks=False):
        if 'daily' in root or 'weekly' in root or 'monthly' in root or 'yearly' in root:
            # Retrieve the folder name to save what the frequency of the usagestats were:
            frequency = root.split('/')[-1]
            for filename in filenames:
                # Check if filename is only numbers (which is an epoch time representation)
                if filename.isnumeric():
                    try:
                        tree = ET.parse(os.path.join(root, filename))
                    except ET.ParseError:
                        parse_file_with_protobuf(os.path.join(root, filename), db)
                        continue

                    # We have sucessfully parsed the usagestats xml.
                    # So continue processing
                    tree_root = tree.getroot()

                    for elem in tree_root:
                        parse_sub_elements(frequency, elem, filename, db)

        # query for reporting
        cursor.execute('''
        select 
        usage_type,
        datetime(lastime/1000, 'UNIXEPOCH', 'localtime') as lasttimeactive,
        timeactive as time_Active_in_msecs,
        timeactive/1000 as timeactive_in_secs,
        case last_time_service_used  WHEN '' THEN ''
         ELSE datetime(last_time_service_used/1000, 'UNIXEPOCH', 'localtime')
        end last_time_service_used,
        case last_time_visible  WHEN '' THEN ''
         ELSE datetime(last_time_visible/1000, 'UNIXEPOCH', 'localtime') 
        end last_time_visible,
        total_time_visible,
        app_launch_count,
        package,
        CASE types
             WHEN '1' THEN 'MOVE_TO_FOREGROUND'
             WHEN '2' THEN 'MOVE_TO_BACKGROUND'
             WHEN '5' THEN 'CONFIGURATION_CHANGE'
             WHEN '7' THEN 'USER_INTERACTION'
             WHEN '8' THEN 'SHORTCUT_INVOCATION'
             ELSE types
        END types,
        classs,
        source,
        fullatt
        from data
        order by lasttimeactive DESC
        ''')
        all_rows = cursor.fetchall()

        # HTML report section
        h = open('./Report.html', 'w')
        h.write('<html><body>')
        h.write('<h2>Android Usagestats report (Dates are localtime!)</h2>')
        h.write('<style> table, th, td {border: 1px solid black; border-collapse: collapse;}</style>')
        h.write('<br />')

        # HTML headers
        h.write('<table>')
        h.write('<tr>')
        h.write('<th>Usage Type</th>')
        h.write('<th>Last Time Active</th>')
        h.write('<th>Time Active in Msecs</th>')
        h.write('<th>Time Active in Secs</th>')
        h.write('<th>Last Time Service Used</th>')
        h.write('<th>Last Time Visible</th>')
        h.write('<th>Total Time Visible</th>')
        h.write('<th>App Launch Count</th>')
        h.write('<th>Package</th>')
        h.write('<th>Types</th>')
        h.write('<th>Class</th>')
        h.write('<th>Source</th>')
        h.write('</tr>')

        for row in all_rows:
            usage_type = row[0]
            lasttimeactive = row[1]
            time_Active_in_msecs = row[2]
            timeactive_in_secs = row[3]
            last_time_service_used = row[4]
            last_time_visible = row[5]
            total_time_visible = row[6]
            app_launch_count = row[7]
            package = row[8]
            types = row[9]
            classs = row[10]
            source = row[11]

            processed = processed + 1
            # report data
            h.write('<tr>')
            h.write('<td>' + str(usage_type) + '</td>')
            h.write('<td>' + str(lasttimeactive) + '</td>')
            h.write('<td>' + str(time_Active_in_msecs) + '</td>')
            h.write('<td>' + str(timeactive_in_secs) + '</td>')
            h.write('<td>' + str(last_time_service_used) + '</td>')
            h.write('<td>' + str(last_time_visible) + '</td>')
            h.write('<td>' + str(total_time_visible) + '</td>')
            h.write('<td>' + str(app_launch_count) + '</td>')
            h.write('<td>' + str(package) + '</td>')
            h.write('<td>' + str(types) + '</td>')
            h.write('<td>' + str(classs) + '</td>')
            h.write('<td>' + str(source) + '</td>')
            h.write('</tr>')

        # HTML footer
        h.write('<table>')
        h.write('<br />')

        print('')
        print('Records processed: ' + str(processed))
        print('Triage report completed. See Reports.html.')


if __name__ == '__main__':
    # For testing purposes, use script directory
    usagestats_parse(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'usagestats'))
