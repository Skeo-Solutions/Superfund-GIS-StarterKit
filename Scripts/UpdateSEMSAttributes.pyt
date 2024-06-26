# -*- coding: utf-8 -*-

import arcpy
import requests
import os, sys, datetime, json, traceback, re
from operator import itemgetter
from arcpy import env

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Update SEMS Attributes"
        self.alias = "UpdateSEMSAttributes"

        # List of tool classes associated with this toolbox
        self.tools = [UpdateSEMSTool]

class UpdateSEMSTool(object):

    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Update SEMS Tool"
        self.description = "This tool queries the SEMS API for matching sites and updates the corresponding attributes of the input feature class."
        self.canRunInBackground = False

        self.semsRegionFieldName = 'region'
        self.semsEpaIdFieldName = 'epaId'
        self.featureRegionFieldName = ""
        self.featureEpaIdFieldName = ""
        self.featureFields = []
        self.featureToSemsfieldMap = {
            'REGION_CODE':['region'],
            'EPA_ID':['epaId'],
            'SITE_NAME': ['sitename'],
            'CITY_NAME': ['city'],
            'COUNTY': ['county'],
            'STATE_CODE': ['statecode'],
            'ZIP_CODE': ['zipcode'],
            'SITE_CONTACT_NAME': ['contactFirstName','contactLastName'],
            'PRIMARY_TELEPHONE_NUM': ['contactPhone'],
            'SITE_CONTACT_EMAIL': ['contactEmailAddress'],
            'STREET_ADDR_TXT': ['address'],
            'NPL_STATUS_CODE': ['nplstatuscode'],
            'FEDERAL_FACILITY_DETER_CODE': ['federalfacilityindicator'],
            'URL_ALIAS_TXT': ['friendly_url'],
            'SITE_ID':['siteId'],
        }
        self.featureFieldLengths = {}


        # set variables for use in other function
        self.SemsfieldRequired = [
             'EPA_ID']
        self.SemsfieldForUpdate = [
             'SITE_NAME',
             'CITY_NAME',
             'COUNTY',
             'STATE_CODE',
             'ZIP_CODE',
             'SITE_CONTACT_NAME',
             'PRIMARY_TELEPHONE_NUM',
             'SITE_CONTACT_EMAIL',
             'STREET_ADDR_TXT',
             'NPL_STATUS_CODE',
             'FEDERAL_FACILITY_DETER_CODE',
             'URL_ALIAS_TXT',
             'SITE_ID',
             'REGION_CODE']

        #This to translate JSON API fields to arc table fields
        
        self.contactTransform = {
            'firstname':'contactFirstName',
            'lastname':'contactLastName',
            'phone': 'contactPhone',
            'email': 'contactEmailAddress',
            'role': 'contactType'
        }

        self.regionLookup = {
            "01": ["CT", "MA", "ME", "NH", "RI", "VT"],  
            "02": ["NJ", "NY", "PR", "VI"],              
            "03": ["DC", "DE", "MD", "PA", "VA", "WV"],  
            "04": ["AL", "FL", "GA", "KY", "MS", "NC", "SC", "TN"],  
            "05": ["IL", "IN", "MI", "MN", "OH", "WI"],  
            "06": ["AR", "LA", "NM", "OK", "TX"],        
            "07": ["IA", "KS", "MO", "NE"],              
            "08": ["CO", "MT", "ND", "SD", "UT", "WY"],  
            "09": ["AS", "AZ", "CA", "GU", "HI", "MP", "NV", "FM", "NN"],  
            "10": ["AK", "ID", "OR", "WA"]               
        }


        self.params = arcpy.GetParameterInfo()

        self.inLineParameter = self.params

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Input Features",
            name="in_features",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input",
            multiValue=True)
        return [param0]

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        # Validation routine - checks to make sure that the lookup fields (EPA_ID) are present
        # and that at least one other field is present to update.
        if parameters[0].valueAsText is not None:
            fcList = parameters[0].valueAsText.replace("'","").split(";")

            for fc in fcList:
                listedFCfields = arcpy.ListFields(fc)
                listedFCFieldNames = []
                missingEssentialFields = ""

                for fcField in listedFCfields:
                    listedFCFieldNames.append(fcField.name)
                for requiredField in self.SemsfieldRequired:
                    if not (requiredField in listedFCFieldNames):
                        missingEssentialFields = missingEssentialFields + requiredField + ","
                if (missingEssentialFields!=""):
                    parameters[0].setErrorMessage("The following required field(s): " + missingEssentialFields + " do not exist in " + fc)
                else:
                    noFieldToUpdate = True
                    for fieldTobeUpdated in self.SemsfieldForUpdate:
                        if (fieldTobeUpdated in listedFCFieldNames):
                            noFieldToUpdate = False
                            break
                    if noFieldToUpdate == True:
                        parameters[0].setErrorMessage("No fields to update for " + fc)
        return
    
    def updateFeatureClass(self, fc, data):
        # Updates the feature class using the API response.
        workspace = arcpy.Describe(fc).path
        editing = False
        try:
            # Start an edit session. Must provide the workspace.
            edit = arcpy.da.Editor(workspace)
            # Edit session is started without an undo/redo stack for versioned data
            datasetVersioned = arcpy.Describe(fc).isVersioned
            edit.startEditing(with_undo=False, multiuser_mode=datasetVersioned)
            # Start an edit operation
            edit.startOperation()
            editing = True
        except:
            pass

        #regionInteger = str(data[self.semsRegionFieldName]).strip("0")
        #paddedRegion = str(data[self.semsRegionFieldName])
        #expression = self.featureRegionFieldName + " IN ('" + regionInteger + "', '" + paddedRegion +  "') AND " + self.featureEpaIdFieldName + " = '" + data[self.semsEpaIdFieldName] + "'"
        #expression = "{} IN ('{}', '{}') AND {} = '{}'".format(self.featureRegionFieldName, regionInteger, paddedRegion, self.featureEpaIdFieldName, self.semsEpaIdFieldName)
        expression = self.featureEpaIdFieldName + " = '" + data[self.semsEpaIdFieldName] + "'"
        cursor = arcpy.da.UpdateCursor(fc, self.featureFields, expression)

        # Track whether any edits were made - if none, then all attribute data in the feature class matched the API for this site.
        rowUpdated = False
        for row in cursor:
            rowindex = -1
            for featureField in self.featureFields:
                rowindex = rowindex + 1
                semsFields = self.featureToSemsfieldMap[featureField]
                # Allows for mapping two SEMS fields to one Feature Class field (Contact Name)
                firstSemsField = semsFields[0]
                #if region field or epa id field we don't need to update
                if firstSemsField in [self.semsEpaIdFieldName]: continue

                val = ''
                if firstSemsField in data:
                    val = data[firstSemsField]
                # Combines Firstname and Lastname
                if len(semsFields) > 1:
                    if semsFields[1] in data:
                        val = str(val) + ' ' + str(data[semsFields[1]])

                #field might be limited string field. just clip off any characters over limt
                if val and featureField in self.featureFieldLengths and isinstance(val, str) and len(val) > self.featureFieldLengths[featureField]:
                    val = val[:self.featureFieldLengths[featureField]]

                if (row[rowindex] != val):
                    rowUpdated = True
                    arcpy.AddMessage("In {} changed {} from {} to {}".format(fc,featureField,str(row[rowindex]),str(val)))
                    row[rowindex] = val
            cursor.updateRow(row)
        del cursor

        if (editing):
            # Stop the edit operation.
            edit.stopOperation()
            # Stop the edit session and save the changes
            edit.stopEditing(save_changes=True)

        return rowUpdated

    def parseSiteInstances(self,semsResponse,primaryYN):
        siteInstances = []
        for siteObj in semsResponse['data']:
            if siteObj['friendly_url']:
                if not siteObj['friendly_url'].startswith(('https://','http://')):
                    siteObj['friendly_url'] = 'https://' + siteObj['friendly_url']

            if siteObj['region']:
                siteObj['region'] = int(siteObj['region'])

            if siteObj['siteContact']:
                filteredContacts = [contact for contact in siteObj['siteContact'] if contact["role"] == "Remedial Project Manager (RPM)"]
                if len(filteredContacts) > 0:
                        sortedContacts = sorted(filteredContacts, key=lambda k: k['lastname'])
                        primaryContact = [contact for contact in sortedContacts if contact["primary"] == "Y"]
                        if len(primaryContact) > 0:
                            siteContact = primaryContact[0]
                        else:
                            siteContact = sortedContacts[0]
                        for contactField in self.contactTransform:
                            siteObj[self.contactTransform[contactField]] = siteContact[contactField]

            #convert GeographicCoordinate to array
            # API has / delimited Geographic coordinate string like:
            # lat/long/collectionDate/primaryIndicator/geographicCoordinateId
            # potentially problematic because sometimes collection date is empty and therefore splitting on / produces different array length
            if siteObj['GeographicCoordinate']:
                GeographicCoordinateArray = siteObj['GeographicCoordinate'].split("/")
                arrayLength = len(GeographicCoordinateArray)
                if arrayLength < 6:
                    print (GeographicCoordinateArray)
                    siteObj['collectionDate'] = GeographicCoordinateArray[2]
                    siteObj['primaryIndicator'] = GeographicCoordinateArray[3]
                    siteObj['geographicCoordinateId'] = GeographicCoordinateArray[4]
                else:
                    siteObj['collectionDate'] = GeographicCoordinateArray[2] + '/' + GeographicCoordinateArray[3] + '/' + GeographicCoordinateArray[4]
                    siteObj['primaryIndicator'] = GeographicCoordinateArray[5]
                    siteObj['geographicCoordinateId'] = GeographicCoordinateArray[6]

            if primaryYN:
                #only consider sites with primary indicator = Y
                if siteObj['primaryIndicator']=='Y': siteInstances.append(siteObj)
            else:
                # if no instances are primary, add all.
                siteInstances.append(siteObj)


        return siteInstances

    def execute(self, parameters, messages):

        # List of regional Superfund feature classes to have attributes updated from SEMS

        fcList = parameters[0].valueAsText.replace("'","").split(";")

        self.featureFields = list(self.featureToSemsfieldMap.keys())

        #sometimes need to map backwards
        semsToFeatureFieldMap = {}

        for featureField in self.featureFields:
            semsFields = self.featureToSemsfieldMap[featureField]
            #can't reverse map feature fields that are made up of multiple sems fields
            if len(semsFields)!=1: continue

            semsToFeatureFieldMap[semsFields[0]] = featureField

        self.featureRegionFieldName = semsToFeatureFieldMap[self.semsRegionFieldName]
        self.featureEpaIdFieldName = semsToFeatureFieldMap[self.semsEpaIdFieldName]

        #was testing this to figure out how they used to use codes instead of text for npl status
        #but now sems api is returning text instead of code so we don't need to use it anymore
        FGDB_WKPS = arcpy.Describe(fcList[0]).path
        descPath = arcpy.Describe(FGDB_WKPS)
        if hasattr(descPath, 'dataType'):
            if descPath.dataType == 'FeatureDataset':
                FGDB_WKPS = descPath.path
        domainsList = arcpy.da.ListDomains(FGDB_WKPS)
        self.featureFieldLengths = {}

        #----- Extract data from SEMS via JSON service -----

        try:
            #JSON url from the production server
            url="https://semspub.epa.gov/src/sitedetails/"
            headers = {'content-type': 'application/json'}

            def _removeNonAscii(field): return "".join(i for i in field if ord(i)<128)

            featuresToSitesMap = {} # sites in the region
            editTracker = {}
            for fc in fcList:
                editTracker[fc] = []
                #Get feature field lengths if string
                listedFCfields = arcpy.ListFields(fc)
                self.featureFieldLengths = {}
                for fcField in listedFCfields:
                    if fcField.name in self.featureFields and fcField.type.lower() == 'string' :
                        self.featureFieldLengths[fcField.name] = fcField.length
                with arcpy.da.SearchCursor(fc,[self.featureEpaIdFieldName]) as cursor:
                    rownum = 0
                    for row in cursor:
                        rownum += 1
                        if row[0]:
                            stateCode = row[0][:2]
                            regionLookup = [k for k,v in self.regionLookup.items() if stateCode in v][0]
                            regionEpaId = regionLookup + '/' + row[0]
                            if regionEpaId in featuresToSitesMap:
                                if fc not in featuresToSitesMap[regionEpaId]:
                                    featuresToSitesMap[regionEpaId].append(fc)
                            else:
                                featuresToSitesMap[regionEpaId] = [fc]
                        else:
                            arcpy.AddMessage("The site in row {} is missing EPA ID values required for SEMS API query and will not be updated".format(rownum))

            siteCount=0

            for site in list(featuresToSitesMap.keys()):
                #for testing just one site
                # if not site == '07/MOD098633415': continue
                arcpy.AddMessage(str(datetime.datetime.now()) + " Querying API for site details https://semspub.epa.gov/src/sitedetails/" + site)

                response = requests.get(url + site,headers=headers)

                try:
                    semsResponse = json.loads(response.content)
                except:
                    arcpy.AddWarning('site = {} could not be retrieved from the SEMS API. The response was : {}'.format(site,response.content))

                    continue

                siteCount += 1
                arcpy.AddMessage(str(datetime.datetime.now()) + " Processing API response")

                siteInstances = self.parseSiteInstances(semsResponse,True)
                if (len(siteInstances) < 1):
                    siteInstances = self.parseSiteInstances(semsResponse,False)

                # Deal with duplicates by sorting by colectionDate,geographicCoordinateId
                # will keep site instance with latest collection date and geo coord ID
                siteInstances.sort(key=itemgetter('collectionDate', 'geographicCoordinateId'),reverse=True)

                latestSiteInstance = siteInstances[0]

                #now update the feature class for this site
                for fc in featuresToSitesMap[site]:
                    edited = self.updateFeatureClass(fc,latestSiteInstance)
                    if edited:
                        editTracker[fc].append(site)

            arcpy.AddMessage(str(datetime.datetime.now()) + " The script completed extracting SEMS data successfully.")
            arcpy.AddMessage("There were {} unique queries to the SEMS API.".format(str(len(featuresToSitesMap.keys()))))
            for fc in list(editTracker.keys()):
                if len(editTracker[fc]) > 0:
                    arcpy.AddMessage("The following {} sites in {} were updated: {}. All other sites matched SEMS.".format(len(editTracker[fc]),fc,", ".join(editTracker[fc])))
                else:
                    arcpy.AddMessage("All sites in {} matched SEMS and no updates were made.".format(fc))
        except Exception as e:

            arcpy.AddError(str(datetime.datetime.now()) + " Error - " + str(e))

            traceback.print_exception(*sys.exc_info())

            exit()


