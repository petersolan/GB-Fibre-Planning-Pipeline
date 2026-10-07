<?xml version="1.0" encoding="UTF-8"?>
<!-- Road links coloured by people without gigabit per km; unranked links thin grey. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>road_link_priority</Name>
    <UserStyle>
      <Title>Fibre build priority</Title>
      <FeatureTypeStyle>
        <Rule>
          <Title>No people without gigabit</Title>
          <ogc:Filter><ogc:PropertyIsNull><ogc:PropertyName>priority_rank</ogc:PropertyName></ogc:PropertyIsNull></ogc:Filter>
          <LineSymbolizer><Stroke><CssParameter name="stroke">#9aa0a6</CssParameter><CssParameter name="stroke-width">0.6</CssParameter><CssParameter name="stroke-opacity">0.6</CssParameter></Stroke></LineSymbolizer>
        </Rule>
        <Rule>
          <Title>Under 100 people per km</Title>
          <ogc:Filter><ogc:And>
            <ogc:Not><ogc:PropertyIsNull><ogc:PropertyName>priority_rank</ogc:PropertyName></ogc:PropertyIsNull></ogc:Not>
            <ogc:PropertyIsLessThan><ogc:PropertyName>people_per_km</ogc:PropertyName><ogc:Literal>100</ogc:Literal></ogc:PropertyIsLessThan>
          </ogc:And></ogc:Filter>
          <LineSymbolizer><Stroke><CssParameter name="stroke">#fdd49e</CssParameter><CssParameter name="stroke-width">2</CssParameter></Stroke></LineSymbolizer>
        </Rule>
        <Rule>
          <Title>100 to 500 people per km</Title>
          <ogc:Filter><ogc:PropertyIsBetween><ogc:PropertyName>people_per_km</ogc:PropertyName>
            <ogc:LowerBoundary><ogc:Literal>100</ogc:Literal></ogc:LowerBoundary>
            <ogc:UpperBoundary><ogc:Literal>500</ogc:Literal></ogc:UpperBoundary>
          </ogc:PropertyIsBetween></ogc:Filter>
          <LineSymbolizer><Stroke><CssParameter name="stroke">#fc8d59</CssParameter><CssParameter name="stroke-width">3</CssParameter></Stroke></LineSymbolizer>
        </Rule>
        <Rule>
          <Title>Over 500 people per km</Title>
          <ogc:Filter><ogc:PropertyIsGreaterThan><ogc:PropertyName>people_per_km</ogc:PropertyName><ogc:Literal>500</ogc:Literal></ogc:PropertyIsGreaterThan></ogc:Filter>
          <LineSymbolizer><Stroke><CssParameter name="stroke">#b30000</CssParameter><CssParameter name="stroke-width">4</CssParameter></Stroke></LineSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
