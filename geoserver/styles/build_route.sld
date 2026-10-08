<?xml version="1.0" encoding="UTF-8"?>
<!-- Proposed cable network: connecting routes blue (darker and wider where they serve 100+ people), gap streets red. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>build_route</Name>
    <UserStyle>
      <Title>Proposed fibre build network</Title>
      <FeatureTypeStyle>
        <Rule>
          <Title>Connecting route (under 100 people served)</Title>
          <ogc:Filter><ogc:And>
            <ogc:PropertyIsEqualTo><ogc:PropertyName>role</ogc:PropertyName><ogc:Literal>connection</ogc:Literal></ogc:PropertyIsEqualTo>
            <ogc:PropertyIsLessThan><ogc:PropertyName>people_served</ogc:PropertyName><ogc:Literal>100</ogc:Literal></ogc:PropertyIsLessThan>
          </ogc:And></ogc:Filter>
          <LineSymbolizer><Stroke><CssParameter name="stroke">#1f78b4</CssParameter><CssParameter name="stroke-width">4</CssParameter></Stroke></LineSymbolizer>
        </Rule>
        <Rule>
          <Title>Connecting route (100+ people served)</Title>
          <ogc:Filter><ogc:And>
            <ogc:PropertyIsEqualTo><ogc:PropertyName>role</ogc:PropertyName><ogc:Literal>connection</ogc:Literal></ogc:PropertyIsEqualTo>
            <ogc:PropertyIsGreaterThanOrEqualTo><ogc:PropertyName>people_served</ogc:PropertyName><ogc:Literal>100</ogc:Literal></ogc:PropertyIsGreaterThanOrEqualTo>
          </ogc:And></ogc:Filter>
          <LineSymbolizer><Stroke><CssParameter name="stroke">#08306b</CssParameter><CssParameter name="stroke-width">6</CssParameter></Stroke></LineSymbolizer>
        </Rule>
        <Rule>
          <Title>Gap street (no gigabit)</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>role</ogc:PropertyName><ogc:Literal>gap</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
          <LineSymbolizer><Stroke><CssParameter name="stroke">#d7301f</CssParameter><CssParameter name="stroke-width">3</CssParameter></Stroke></LineSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
