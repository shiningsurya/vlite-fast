"""
Downloaded from 
http://code.activestate.com/recipes/410469-xml-as-dictionary/

Written by Duncan McGreggor

Modified to work with antprop which has duplicate elements with same tag which confuses this code
original code just overwrites
"""

from xml.etree import ElementTree

# I don't use this 
class XmlListConfig(list):
    def __init__(self, aList):
        for element in aList:
            if element:
                # treat like dict
                if len(element) == 1 or element[0].tag != element[1].tag:
                    self.append(XmlDictConfig(element))
                # treat like list
                elif element[0].tag == element[1].tag:
                    self.append(XmlListConfig(element))
            elif element.text:
                text = element.text.strip()
                if text:
                    self.append(text)


class XmlDictConfig(dict):
    '''
    Example usage:

    >>> tree = ElementTree.parse('your_file.xml')
    >>> root = tree.getroot()
    >>> xmldict = XmlDictConfig(root)

    Or, if you want to use an XML string:

    >>> root = ElementTree.XML(xml_string)
    >>> xmldict = XmlDictConfig(root)

    And then use xmldict for what it is... a dict.
    '''
    def __init__(self, parent_element):
        DDict= dict()
        # parses config, datasetId, creation
        if parent_element.items():
            self.update(dict(parent_element.items()))
        for element in parent_element:
            # earth orientation parameter
            if element.tag == "EopSet":
                edict = dict ()
                for e in element:
                    # this is eopday
                    epc = e.find('epoch').text
                    edict[epc] = {etag:e.find(etag).text for etag in ['tai_utc', 'ut1_utc', 'x_pole', 'y_pole']}
                self.update ({'eopset':edict})
            # antenna properties
            elif element.tag == "AntennaProperties":
                #### XXX assuming there is only one item
                [name, ant], = element.items()
                dant = dict ()
                for e in element:
                    dant[e.tag] = e.text
                DDict[ant] = dant
            # any other case is errorenous
            else:
                pass
        self.update ({'ants': DDict})
