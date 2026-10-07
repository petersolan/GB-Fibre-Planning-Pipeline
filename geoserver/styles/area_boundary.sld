<?xml version="1.0" encoding="UTF-8"?>
<!-- Planning area: outline only, so the layers underneath stay visible. -->
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc"
    xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>area_boundary</Name>
    <UserStyle>
      <Title>Planning area outline</Title>
      <FeatureTypeStyle>
        <Rule>
          <PolygonSymbolizer>
            <Stroke><CssParameter name="stroke">#3366cc</CssParameter><CssParameter name="stroke-width">2</CssParameter><CssParameter name="stroke-dasharray">8 4</CssParameter></Stroke>
          </PolygonSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
