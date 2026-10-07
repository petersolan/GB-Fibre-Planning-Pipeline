<?xml version="1.0" encoding="UTF-8"?>
<!-- Premises as small dots: green with gigabit, red without, grey if unknown. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>premises</Name>
    <UserStyle>
      <Title>Gigabit coverage by premises</Title>
      <FeatureTypeStyle>
        <Rule>
          <Title>Postcode fully covered</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>gigabit_pct</ogc:PropertyName><ogc:Literal>100</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
          <MaxScaleDenominator>25000</MaxScaleDenominator>
          <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#1a9850</CssParameter></Fill></Mark><Size>4</Size></Graphic></PointSymbolizer>
        </Rule>
        <Rule>
          <Title>Postcode partly covered</Title>
          <ogc:Filter><ogc:And>
            <ogc:PropertyIsGreaterThan><ogc:PropertyName>gigabit_pct</ogc:PropertyName><ogc:Literal>0</ogc:Literal></ogc:PropertyIsGreaterThan>
            <ogc:PropertyIsLessThan><ogc:PropertyName>gigabit_pct</ogc:PropertyName><ogc:Literal>100</ogc:Literal></ogc:PropertyIsLessThan>
          </ogc:And></ogc:Filter>
          <MaxScaleDenominator>25000</MaxScaleDenominator>
          <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#fdae61</CssParameter></Fill></Mark><Size>5</Size></Graphic></PointSymbolizer>
        </Rule>
        <Rule>
          <Title>No gigabit in postcode</Title>
          <ogc:Filter><ogc:PropertyIsEqualTo><ogc:PropertyName>gigabit_pct</ogc:PropertyName><ogc:Literal>0</ogc:Literal></ogc:PropertyIsEqualTo></ogc:Filter>
          <MaxScaleDenominator>25000</MaxScaleDenominator>
          <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#d73027</CssParameter></Fill></Mark><Size>6</Size></Graphic></PointSymbolizer>
        </Rule>
        <Rule>
          <Title>No Ofcom data</Title>
          <ogc:Filter><ogc:PropertyIsNull><ogc:PropertyName>gigabit_pct</ogc:PropertyName></ogc:PropertyIsNull></ogc:Filter>
          <MaxScaleDenominator>25000</MaxScaleDenominator>
          <PointSymbolizer><Graphic><Mark><WellKnownName>circle</WellKnownName><Fill><CssParameter name="fill">#9aa0a6</CssParameter></Fill></Mark><Size>4</Size></Graphic></PointSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
