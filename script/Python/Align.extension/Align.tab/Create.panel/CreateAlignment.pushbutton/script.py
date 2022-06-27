import math
import re
import clr

clr.AddReference("PresentationCore")

import System
from System.Collections.ObjectModel import ObservableCollection

import rpw
from rpw import revit, db, ui, DB, UI

from rpw.exceptions import RevitExceptions
from pyrevit.forms import WPFWindow
from collections import Iterable

from event import CustomizableEvent

import verticalcurve
import excel
import geometry as factory

"""
General Information Start
"""
__doc__ = "Alignment Manager"
__title__ = "Create Alignment Model"
__author__ = "DY Lim"
__persistentengine__ = True
"""
General Information End
"""
"""
Global Variables Start
"""
curveType = ["Line", "Curve"]
customizable_event = CustomizableEvent()
selectCond= True
horizAlignment, updatedHorzAlignment = [], False
interGeometry = []
internal_alignment = False
SubLines, updatedSubLines = [], False
intersectionPoints = []
ReferencePoint = []
"""
Global Variables End
"""
"""
General Functions Start
"""
def debug(self, line):
    self.debug.Text = "{}\n{}".format(self.debug.Text, line)
    self.debug.ScrollToEnd()

def debugHorizontal(self, line):
    self.HorizontalLog.Text = "{}\n{}".format(self.HorizontalLog.Text, line)
    self.HorizontalLog.ScrollToEnd()

def toFloat(input):
    try:
        return float(input)
    except:
        return None

def Flatten(x):
    if isinstance(x, Iterable):
        return [a for i in x for a in Flatten(i)]
    else:
        return [x]

def ft2mm(ft):
    return ft * 304.8
"""
General Functions End
"""
"""
Revit API Methods Start
"""
class FamOpt1(DB.IFamilyLoadOptions):
    def __init__(self):
        pass
    def OnFamilyFound(self,familyInUse, overwriteParameterValues):
        return True
    def OnSharedFamilyFound(self,familyInUse, source, overwriteParameterValues):
        return True

def get_levels(doc):
    levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
    sortedLevels = sorted(levels,key=lambda level : level.Elevation, reverse=True)
    # elevation = [ft2mm(i.Elevation) for i in sortedLevels]
    return sortedLevels

### WIP Convert to Survey Point based Coordinate
# def get_PBPLocation():
#     surveyPoint = DB.BasePoint.GetSurveyPoint(revit.doc).Position
#     ProjectBasePoint = DB.BasePoint.GetProjectBasePoint(revit.doc).Position
#     return DB.XYZ((0 - surveyPoint.X + ProjectBasePoint.X), (0 - surveyPoint.Y + ProjectBasePoint.Y), (0 - surveyPoint.Z + ProjectBasePoint.Z))

def select_horizAlignment():
    global horizAlignment, updatedHorzAlignment
    with db.Transaction("selection"):
        ref = ui.Pick.pick_element("Select Reference", True)
        try:
            horizAlignment = [revit.doc.GetElement(r.ElementId) for r in ref]
            updatedHorzAlignment = True
        except:
            updatedHorzAlignment = False

def select_SubLines():
    global SubLines, updatedSubLines
    with db.Transaction("selection"):
        ref = ui.Pick.pick_element("Select Reference", True)
        try:
            SubLines = [revit.doc.GetElement(r.ElementId) for r in ref]
            updatedSubLines = True
        except:
            updatedSubLines = False

def createReferencePoint(self, famdoc, points):
    try:
        stations = [str(i.Station) for i in self.PointContents]
        levelRef = get_levels(famdoc)[0].GetPlaneReference()
        ProjectLevelRef = get_levels(revit.doc)[0].GetPlaneReference()
        ids=[]
    except Exception as e:
        UI.TaskDialog.Show("Error", "Get General Parameter Failed : {}".format(e))

    with db.Transaction("Create Reference Points"):
        try:
            t = DB.Transaction(famdoc)
            t.Start("Create Reference Point")
            for s, pt in zip(stations, points):
                pointRef = DB.PointOnPlane.NewPointOnPlane(famdoc, levelRef, DB.XYZ(pt.X * 0.00328084, pt.Y * 0.00328084, 0), DB.XYZ(1,0,0))
                refPoint = famdoc.FamilyCreate.NewReferencePoint(pointRef)
                refPoint.Visible = True
                refPoint.Name = "{}/{}".format(s, refPoint.UniqueId)
                ids.append(refPoint.UniqueId)
            t.Commit()
        except Exception as e:
            UI.TaskDialog.Show("Error", "Create Reference Point Error : {}".format(e))
            t.Commit()
        try:
            documentLocation = (revit.doc.PathName).Split('\\')
            documentLocation = '{}{}'.format('\\'.join(map(str, documentLocation[0:-1])),'\\')
            saveAsPath = "{}{}.rfa".format(documentLocation, "Alignment")
            SaveAsOpt = DB.SaveAsOptions()
            SaveAsOpt.OverwriteExistingFile = True
            famdoc.SaveAs(saveAsPath, SaveAsOpt)
        except Exception as e:
            UI.TaskDialog.Show("Error", "Error while saving : {}".format(e))
    family1 = famdoc.LoadFamily(revit.doc, FamOpt1())
    famdoc.Close(False)
    try:
        familyType = [revit.doc.GetElement(id) for id in family1.GetFamilySymbolIds()]
        with db.Transaction("Place Alignment into Project"):
            familyType[0].Activate()
            # revit.doc.Create.NewFamilyInstance(ProjectLevelRef, DB.XYZ(0,0,0), DB.XYZ(1,0,0), familyType[0])
            e = DB.AdaptiveComponentInstanceUtils.CreateAdaptiveComponentInstance(revit.doc, familyType[0])
            e.Location.Point = DB.XYZ(0, 0, 0)
            UI.TaskDialog.Show("Error", "Created : {}".format(e))
    except Exception as e:
        UI.TaskDialog.Show("Error", "Error while placing family : {}".format(e))
    
    try:
        for i in self.PointContents:
            i.RevitID = ids[i.Index]
            i.IsLoaded = True
    except Exception as e:
        UI.TaskDialog.Show("Error", "Error while parsing data : {}".format(e))
"""
Revit API Methods End
"""
"""
WPF Data Table Format Start
"""
class verticalAlignmentFormat:
    def __init__(
        self,
        index=None,
        pviStation=None,
        pviElevation=None,
        grade=None,
        _CurveType=None,
        _CurveLength=None,
        _K=None,
    ):
        self.index = index
        self.pviStation = pviStation
        self.pviElevation = pviElevation
        self.grade = grade
        self._CurveType = _CurveType
        self._CurveLength = _CurveLength
        self._K = _K

class horizontalAlignmentFormat:
    def __init__(self, index, type, start, end, length, direction=None, radius=None):
        self.Index = index
        self.CurveType = type
        self.StartStation = start
        self.EndStation = end
        self.Length = length
        self.Direction = direction
        self.Radius = radius

class horizontalPointTableFormat:
    def __init__(self, index, station, revitID=None, isloaded=False):
        self.Index = index
        self.Station = station
        self.RevitID = revitID
        self.IsLoaded = isloaded
"""
WPF Data Table Format End
"""
"""
Main Start From Here
"""
class form_window(WPFWindow):
    def __init__(self, xaml_file_name):
        WPFWindow.__init__(self, xaml_file_name)
        self.Show()

        self.VAContents = ObservableCollection[object]()
        self.VerticalCurveTable.ItemsSource = self.VAContents

        self.HZContents = ObservableCollection[object]()
        self.HorizontalAlignmentTable.ItemsSource = self.HZContents

        self.PointContents = ObservableCollection[object]()
        self.HorizontalPointsTable.ItemsSource = self.PointContents

        self.curveType = ObservableCollection[object]()
        [self.curveType.Add(ct) for ct in curveType]
        self.input_curveType.ItemsSource = self.curveType

        self.debug.Text = "Initializing Success\nWaiting Task..."
        

    """
    Vertical Curve Interface
    """
    def addrow(self, sender, e):
        curveTypeIndex = self.input_curveType.SelectedIndex
        lastIndex = 0
        for i in self.VAContents:
            try:
                lastIndex = i.index
            except:
                continue
        if curveTypeIndex == 0:
            if lastIndex != 0 and lastIndex % 2 == 0:
                debug(self, "Item Must Be Line Type")
            else:
                if lastIndex == 0:
                    lastIndex = -1
                grade = self.inputValue5.Text
                self.VAContents.Add(
                    verticalAlignmentFormat(
                        lastIndex + 1,
                        None,
                        None,
                        grade,
                        "Line",
                        None,
                        None,
                    )
                )
        elif curveTypeIndex == 1:
            if lastIndex % 2 != 0:
                debug(self, "Item Must Be Curve Type")
            else:
                pviStation = self.inputValue1.Text
                pviElevation = self.inputValue2.Text
                curveLength = self.inputValue3.Text
                self.VAContents.Add(
                    verticalAlignmentFormat(
                        lastIndex + 1,
                        pviStation,
                        pviElevation,
                        None,
                        "Curve",
                        curveLength,
                        None,
                    )
                )
        else:
            debug(self, "Unidentified Curve Type")
        #
        debug(self, "{} Row Added".format(lastIndex + 1))

    def clearRow(self, sender, e):
        selectedIndex = self.VerticalCurveTable.SelectedIndex
        if selectedIndex == -1:
            debug(self, "Please Select Row To Be Cleared".format(selectedIndex))
        else:
            self.VAContents.RemoveAt(selectedIndex)
            self.VAContents.Insert(
                selectedIndex, verticalAlignmentFormat(selectedIndex)
            )
            debug(self, "{} Row Cleared".format(selectedIndex))

    def removeRow(self, sender, e):
        index = self.VAContents.Count - 1
        if index == 0:
            debug(self, "Cannot Remove All")
        else:
            self.VAContents.RemoveAt(index)
            debug(self, "{} Row Removed".format(index))

    def examineRow(self, sender, e):
        selectedIndex = self.VerticalCurveTable.SelectedIndex
        if selectedIndex == -1:
            debug(self, "Please Select Row To Be Cleared".format(selectedIndex))
        else:
            val = self.VAContents.Item[selectedIndex].grade
            type_val = self.VAContents.Item[selectedIndex]._CurveType
            debug(self, "({},{})".format(val, type_val))

    def valueUpdated(self, sender, e):
        colour_grey = System.Windows.Media.Brushes.LightGray
        colour_black = System.Windows.Media.Brushes.Black
        index = self.input_curveType.SelectedIndex
        if index == 0:
            self.inputText1.Text = "PVI Station Start"
            self.inputText2.Text = "PVI Station End"
            self.inputText3.Text = "PVI Elevation Start"
            self.inputText4.Text = "PVI Elevation End"
            self.inputText5.Text = "Line Slope"
            self.inputText4.Foreground = colour_black
            self.inputValue4.IsReadOnly = False
            self.inputText5.Foreground = colour_black
            self.inputValue5.IsReadOnly = False
        else:
            self.inputText1.Text = "PVI Station"
            self.inputText2.Text = "PVI Elevation"
            self.inputText3.Text = "Curve Length"
            self.inputText4.Foreground = colour_grey
            self.inputValue4.IsReadOnly = True
            self.inputText5.Foreground = colour_grey
            self.inputValue5.IsReadOnly = True
        self.inputValue1.Text = ""
        self.inputValue2.Text = ""
        self.inputValue3.Text = ""
        self.inputValue4.Text = ""
        self.inputValue5.Text = ""

    def input1Updated(self, sender, e):
        index = self.input_curveType.SelectedIndex
        if index == 0:
            colour_grey = System.Windows.Media.Brushes.LightGray
            colour_white = System.Windows.Media.Brushes.White
            value1_count = len(self.inputValue1.Text)
            if value1_count > 0:
                self.inputValue5.IsReadOnly = True
                self.inputValue5.Background = colour_grey
            else:
                self.inputValue5.IsReadOnly = False
                self.inputValue5.Background = colour_white

    def input3Updated(self, sender, e):
        index = self.input_curveType.SelectedIndex
        if index == 0 and sender.IsReadOnly == False:
            colour_grey = System.Windows.Media.Brushes.LightGray
            colour_white = System.Windows.Media.Brushes.White
            value5_count = len(self.inputValue5.Text)
            if value5_count > 0:
                self.inputValue1.IsReadOnly = True
                self.inputValue1.Background = colour_grey
                self.inputValue1.Text = ""
                self.inputValue2.IsReadOnly = True
                self.inputValue2.Background = colour_grey
                self.inputValue2.Text = ""
                self.inputValue3.IsReadOnly = True
                self.inputValue3.Background = colour_grey
                self.inputValue3.Text = ""
                self.inputValue4.IsReadOnly = True
                self.inputValue4.Background = colour_grey
                self.inputValue4.Text = ""
            else:
                self.inputValue1.IsReadOnly = False
                self.inputValue1.Background = colour_white
                self.inputValue2.IsReadOnly = False
                self.inputValue2.Background = colour_white
                self.inputValue3.IsReadOnly = False
                self.inputValue3.Background = colour_white
                self.inputValue4.IsReadOnly = False
                self.inputValue4.Background = colour_white

    def inputValue34Updated(self, sender, e):
        index = self.input_curveType.SelectedIndex
        if index == 0:
            pviStationStart = self.inputValue1.Text
            pviStationEnd = self.inputValue2.Text
            pviElevStart = self.inputValue3.Text
            pviElevEnd = self.inputValue4.Text
            condition = all(
                [
                    pviStationStart.replace(".", "", 1).isdigit(),
                    pviStationEnd.replace(".", "", 1).isdigit(),
                    pviElevStart.replace(".", "", 1).replace("-", "", 1).isdigit(),
                    pviElevEnd.replace(".", "", 1).replace("-", "", 1).isdigit(),
                ]
            )
            debug(self, "{}".format(condition))
            if condition:
                xDist = float(pviStationEnd) - float(pviStationStart)
                yDist = float(pviElevEnd) - float(pviElevStart)
                grade = math.atan(yDist / xDist) * 100
                self.inputValue5.Text = str(grade)
    """
    External Data Import Interface
    """
    def selectFile(self, sender, e):
        try:
            path = excel.file_picker()

            self.app = excel.initialise()
            self.workbook = self.app.Workbooks.Add(path)
            self.sheet = [st.Name for st in self.workbook.Sheets]

            self.path.Content = "File Path : {}".format(path)
            self.sheetList.ItemsSource = self.sheet
        except:
            False

    def importSheetData(self, sender, e):
        selectedSheetIndex = self.sheetList.SelectedIndex
        selectedSheet = self.workbook.Sheets(self.sheet[selectedSheetIndex])

        selectedRange = selectedSheet.UsedRange
        values = []
        rowCnt = selectedRange.Rows.Count
        colCnt = selectedRange.Columns.Count
        range(rowCnt)
        for row_py, row_excel in zip(range(rowCnt), range(1, rowCnt + 1)):
            values.append([])
            for col_excel in range(1, colCnt + 1):
                values[row_py].append(selectedRange.Cells(row_excel, col_excel).Value2)

        if "Vertical" in values[0][0]:
            isVerticalData = True
        else:
            isVerticalData = False

        slope = []
        curveLength = []
        pviElevation = []
        pviStation = []
        seStation = []
        sePercentage = []
        curveType = []

        if isVerticalData:
            for row in range(1, rowCnt):
                if row % 2 == 1:
                    slope.append(values[row][1])
                    curveLength.append(None)
                    pviElevation.append(None)
                    pviStation.append(None)
                    curveType.append("Line")
                else:
                    slope.append(None)
                    curveLength.append(values[row][1])
                    pviElevation.append(values[row][2])
                    pviStation.append(values[row][3])
                    curveType.append("Curve")
                seStation.append(values[row][4])
                sePercentage.append(values[row][5])

            for index in range(len(slope)):
                self.VAContents.Add(
                    verticalAlignmentFormat(
                        index,
                        pviStation[index],
                        pviElevation[index],
                        slope[index],
                        curveType[index],
                        curveLength[index],
                        "",
                    )
                )

            self.stationStart.Text = str(seStation[0])
            self.stationEnd.Text = str(seStation[-1])
            self.debug_external.Text = "{}\n{}".format(
                self.debug_external.Text, "Import Success"
            )
        else:
            self.debug_external.Text = "{}\n{}".format(
                self.debug_external.Text, "Under Develop"
            )

        excel.release(self.app)

    def calculateRows(self, sender, e):
        ss = self.stationStart.Text
        se = self.stationEnd.Text
        if ss != "" and se != "" and float(se) > float(ss):
            self.VC = verticalcurve.VerticalCurve(([float(ss), float(se)]))
            debug(self, "{}is loaded".format(self.VC))
            
            pviElevation = [toFloat(g.pviElevation) for g in self.VAContents]
            curveType = [g._CurveType for g in self.VAContents]
            grade = [toFloat(g.grade) for g in self.VAContents]
            curveLength = [toFloat(g._CurveLength) for g in self.VAContents]
            debug(self, "{} and {}".format(grade, curveLength))
            pviStation = [toFloat(g.pviStation) for g in self.VAContents]
            debug(self, "{}".format(pviStation))
            isValidGrade = self.VC.isValidSlope(grade)
            self.VC.CalculateLineTypeAndK(curveLength, grade)
            k = self.VC._K
            ltype = self.VC._CurveType
            debug(self, "{} and {}".format(grade, isValidGrade))
            debug(self, "{} and {}".format(k, ltype))
            self.VC.CalculateCurveLength(pviStation, curveLength, grade)
            debug(self, "Dummy")
            calculatedCurveLength = self.VC._CurveLength
            debug(self, "{}".format(calculatedCurveLength))
            # try:
            for index in range(self.VAContents.Count):
                self.VAContents[index] = verticalAlignmentFormat(
                    index,
                    pviStation[index], 
                    pviElevation[index],
                    grade[index],
                    curveType[index],
                    calculatedCurveLength[index],
                    k[index]
                )
            
            # self.VC.RangeTypeAtStation(stations, curvelength, accumulationrequired=True)
            # except:
            #     debug(self, "Fail")
        else:
            debug(self, "Check Start and End Stations in General")
    """
    Horizontal Curve Interface
    """
    def selectHorzAlignment(self, sender, e):
        global updatedHorzAlignment, horizAlignment
        customizable_event.raise_event(select_horizAlignment)
        self.Refresh.IsEnabled = True
        debugHorizontal(self, "Alignment Selected")
    
    def refreshHroz(self, sender, e):
        global updatedHorzAlignment, horizAlignment, interGeometry, internal_alignment, SubLines, updatedSubLines, intersectionPoints
        intersect = []
        #Main Alignment Refresh Start
        if updatedHorzAlignment == True:
            try:
                #Convert Model Curves to Geomtery
                debugHorizontal(self,"Loaded {} Number of Curves".format(len(horizAlignment)))
                opt = DB.Options()
                opt.ComputeReferences = True
                opt.IncludeNonVisibleObjects = False
                opt.View = revit.doc.ActiveView
                geometry = Flatten([elem.get_Geometry(opt) for elem in horizAlignment])
                geometry = [g for g in geometry]
                crvtype = [g.GetType().Name for g in geometry]
                debugHorizontal(self,"Converted Geometry:{}".format(crvtype))
                updatedHorzAlignment = False

                #Convert Geometry into internal type
                create = factory.CreateEntity()
                for t, g in zip(crvtype, geometry):
                    if t == "Line":
                        tes = g.Tessellate()
                        ptEntity = [factory.PointEntity(ft2mm(p.X), ft2mm(p.Y)) for p in tes]
                        interGeometry.append(factory.LineEntity(ptEntity[0], ptEntity[1]))
                    elif t == "Arc":
                        tes = g.Tessellate()
                        tes = Flatten([tes[0], tes[len(tes)-1], tes[int(len(tes)/2)]])
                        ptEntity = [factory.PointEntity(ft2mm(p.X), ft2mm(p.Y)) for p in tes]
                        interGeometry.append(create.ArcByThreePoints(ptEntity[0], ptEntity[1], ptEntity[2]))
                internal_alignment = factory.PolyCurveEntity(interGeometry)
                if internal_alignment.IsValid:
                    acc = list(factory.Accumulate([crv.Length for crv in internal_alignment.Curves]))
                    acc.insert(0, 0)
                    debugHorizontal(self,"Convert to Internal Geometry Success{}".format(internal_alignment.IsValid))
                else:
                    debugHorizontal(self,"Imported Curves are not continuous!")
                    self.HZContents.Clear()
                    self.Refresh.IsEnabled = False
                    return False

                #Add Geometry into DataTable
                lastIndex = 0
                self.HZContents.Clear()
                for i in self.HZContents:
                    try:
                        lastIndex = i.Index
                    except:
                        continue
                for index, (t, geo) in enumerate(zip(crvtype, interGeometry)):
                    self.HZContents.Add(horizontalAlignmentFormat(lastIndex, t, acc[index], acc[index+1], geo.Length))
                    lastIndex = lastIndex + 1
                
                self.Grd_PointBy.IsEnabled = True
            except:
                debugHorizontal(self,"Loading Horizontal Alignment Failed")
        else:
            debugHorizontal(self,"Horizontal Alignment is not updated.")
        #Sub Line Refresh Start
        if updatedSubLines == True:
            try:
                #Convert Model Curves to Geomtery
                debugHorizontal(self,"Loaded {} Number of Lines".format(len(SubLines)))
                opt = DB.Options()
                opt.ComputeReferences = True
                opt.IncludeNonVisibleObjects = False
                opt.View = revit.doc.ActiveView
                geometry = Flatten([elem.get_Geometry(opt) for elem in SubLines])
                geometry = [g for g in geometry]
                crvtype = [g.GetType().Name for g in geometry]
                updatedSubLines = False

                #Convert Geometry into internal type
                create = factory.CreateEntity()
                for t, g in zip(crvtype, geometry):
                    if t == "Line":
                        tes = g.Tessellate()
                        ptEntity = [factory.PointEntity(ft2mm(p.X), ft2mm(p.Y)) for p in tes]
                        intersect.append(factory.LineEntity(ptEntity[0], ptEntity[1]))
                    else:
                        debugHorizontal(self,"Only Line type is supported.")
                        self.Refresh.IsEnabled = False
                        return False
                for i in intersect:
                    intersectionPoints.append(internal_alignment.IntersectWith(i))
                    intersectionPoints = factory.Flatten(intersectionPoints)
                self.NumIntCrv.Content = "Selected Number of Curves : \n{}".format(len(SubLines))
                self.Pts_Num.Content = "Point Number : {} \nAlignment Length : {}".format(
                    len(intersectionPoints), internal_alignment.Length
                )
            except:
                debugHorizontal(self,"Loading Sub-Lines Failed")
        #After Refresh, disable the button until it is availale
        self.Refresh.IsEnabled = False
            
    def NumberValidationTextBox(self, sender, e):
        if re.search("[^0-9.-]+", e.Text):
            e.Handled = True
        else:
            e.Handled = False
    
    def CalculateNumOfPoints(self, sender, e):
        global internal_alignment
        self.Btn_PBI.IsChecked = True
        try:
            ptsNumber = internal_alignment.Length / float(self.PBI_Interval.Text)
            self.Pts_Num.Content = "Point Number : {} \nAlignment Length : {}".format(
            ptsNumber, internal_alignment.Length
            )
        except:
            False
    
    def Btn_PBC_Checked(self, sender, e):
        colour_grey = System.Windows.Media.Brushes.LightGray

        self.PBI_Interval.Background = colour_grey
        self.PBI_Interval.IsEnabled = False
        self.PBI_Interval.Text = ""
        self.PBC_Btn.IsEnabled = True

    def Btn_PBI_Checked(self, sender, e):
        colour_white = System.Windows.Media.Brushes.White

        self.PBI_Interval.Background = colour_white
        self.PBI_Interval.IsEnabled = True
        self.PBC_Btn.IsEnabled = False

    def BtnClk_PBC(self, sender, e):
        global SubLines, updatedSubLines
        customizable_event.raise_event(select_SubLines)
        self.Btn_PBC.IsChecked = True
        self.Refresh.IsEnabled = True
        debugHorizontal(self, "Sub-Lines Selected")
        
    def Btn_FindPts(self, sender, e):
        global intersectionPoints, internal_alignment
        try:
            lastIndex = 0
            # self.PointsContents.Clear()
            for i in self.PointContents:
                try:
                    lastIndex = i.Index
                except:
                    continue
            #Point By Interval Type
            if self.Btn_PBC.IsChecked:
                for pt in intersectionPoints:
                    station = internal_alignment.SegmentLengthAtPoint(pt)
                    self.PointContents.Add(horizontalPointTableFormat(lastIndex, station))
                    lastIndex = lastIndex + 1
            elif self.Btn_PBI.IsChecked:
                segLength = []
                pointInterval = float(self.PBI_Interval.Text)
                len = 0
                alignment_Length = internal_alignment.Length
                loop = True
                while(loop):
                    if alignment_Length - len < pointInterval:
                        len = alignment_Length
                        loop = False
                    segLength.append(len)
                    if loop == False:
                        intersectionPoints.append(internal_alignment.EndPoint)
                    else:
                        intersectionPoints.append(internal_alignment.PointAtSegmentLength(len))
                    len = len + pointInterval
                for len in segLength:
                    self.PointContents.Add(horizontalPointTableFormat(lastIndex, len))
                    lastIndex = lastIndex + 1
            debugHorizontal(self, "Station Table Updated.")
        except Exception as e:
            debugHorizontal(self, "Find Intersection Points is failed. : {}".format(e))

    def CreatePoint(self, sender, e):
        global intersectionPoints
        try:
            location = revit.app.FamilyTemplatePath
            path = excel.file_picker(False, location, "Metric Generic Model Adaptive.rft")
            self.famdoc = revit.doc.Application.NewFamilyDocument(path)
            customizable_event.raise_event(createReferencePoint, self, self.famdoc, intersectionPoints)
            debugHorizontal(self, "{}".format(path))
        except Exception as e:
            debugHorizontal(self, "File Import Failed : {}".format(e))

    def ToDocument(self, sender, e):
        global ReferencePoint
        debugHorizontal(self, "{}".format(ReferencePoint))
        class FamOpt1(DB.IFamilyLoadOptions):
            def __init__(self):
                pass
            def OnFamilyFound(self,familyInUse, overwriteParameterValues):
                return True
            def OnSharedFamilyFound(self,familyInUse, source, overwriteParameterValues):
                return True
        try:
            documentLocation = (revit.doc.PathName).Split('\\')
            documentLocation = '{}{}'.format('\\'.join(map(str, documentLocation[0:-1])),'\\')
            saveAsPath = "{}{}.rfa".format(documentLocation, "Alignment")
            SaveAsOpt = DB.SaveAsOptions()
            SaveAsOpt.OverwriteExistingFile = True
            self.famdoc.SaveAs(saveAsPath, SaveAsOpt)
            family1 = self.famdoc.LoadFamily(revit.doc, FamOpt1())
            self.famdoc.Close(False)
        except Exception as e:
            debugHorizontal(self, "Error is {}".format(e))
        
        # global internal_alignment
        # try:
        #     float(e.Text)
        #     e.Handled = False
        #     # self.PBI_Num.Content = str(round(internal_alignment.Length / float(self.PBI_Interval.Text),0))
        #     self.PBI_Num.Content = "{}".format(self.PBI_Interval.Text)
        # except:
        #     if e.Text == ".":
        #         e.Handled = False
        #     else:
        #         e.Handled = True
    # def setCurve(self, sender, e):
    #     try:
    #         index = self.layerList.SelectedIndex
    #         debugHorizontal(self,"index{}".format(index))
    #         layers = self.layers
    #         objs = self.objs
    #         selectedCurves = []
    #         hash = []
    #         for obj in objs:
    #             styleId = obj.GraphicsStyleId
    #             style = revit.doc.GetElement(styleId)
    #             try:
    #                 if style.GraphicsStyleCategory.Name == layers[index]:
    #                     selectedCurves.append(obj)
    #                     hash.append(obj.GetHashCode())
    #             except:
    #                 False
    #         list1, list2 = (list(t) for t in zip(*sorted(zip(hash, selectedCurves))))
    #         debugHorizontal(self,"curvenumber:{}".format(selectedCurves))
    #         debugHorizontal(self,"sorted:{}".format(list2))
    #     except:
    #         debugHorizontal(self,"Fail")
        



form = form_window("ui.xaml")
