<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:ieso="http://www.theIMO.com/schema" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
	<xsl:output method="html" version="1.0" encoding="UTF-8" indent="yes"/>
	<xsl:template match="/">
		<xsl:variable name="createdAt">
			<xsl:value-of select="ieso:IMODocument/ieso:IMODocHeader/ieso:CreatedAt"/>
		</xsl:variable>
		<xsl:variable name="deliveryDate">
			<xsl:value-of select="ieso:IMODocument/ieso:IMODocBody/ieso:Date"/>
		</xsl:variable>
		<html>
			<head>
				<script type="text/javascript"> 	
					var cX = 0; var cY = 0;
					function updateCursorPosition(e)
					{ 
						cX = e.pageX; cY = e.pageY;
					}
					function updateCursorPositionDocAll()
					{
						var de = document.documentElement;
						var b = document.body;
						cX = event.clientX + 
							(de.scrollLeft || b.scrollLeft) - (de.clientLeft || 0);
						cY = event.clientY + 
							(de.scrollTop || b.scrollTop) - (de.clientTop || 0);
					}					
					if(document.all) 
					{
						document.onmousemove = updateCursorPositionDocAll; 
					}
					else 
					{
						document.onmousemove = updateCursorPosition; 
					}				
					function assignPosition(d) 
					{
						d.style.left = (cX +10) + "px";
						d.style.top = (cY -30) + "px";
					}				
					function hideHelp(d) 
					{
						document.getElementById(d).style.display = "none";
					}				
					function makeItVisible(d) 
					{
						var dd = document.getElementById(d);
						assignPosition(dd);
						dd.style.display = "block";
					}		
							
				</script>
				<title>
					<xsl:value-of select="ieso:IMODocument/ieso:IMODocHeader/ieso:DocTitle"/>
				</title>
				<link rel="stylesheet" type="text/css" href="https://reports-public.ieso.ca/docrefs/stylesheet/adcs.css"/>
			</head>
			<body>
				<div class="reportHeader">
					<div class="balloon" id="Title" style="display:none; width:420px; height:35px; ">
						The purpose of this report is to publish the total scheduled and actual flows of energy between the IESO Controlled grid and each intertie zone
					</div>
					<div class="balloon" id="Zone" style="display:none; width:580px; height:35px;">
						Intertie Zone. There are fourteen intertie zones representing groups of external interfaces with other jurisdictions(2 for Manitoba, 1 for Michigan, 1 for Minnesota, 1 for New-York state, and 9 for Quebec)
					</div>
					<div class="balloon" id="Interval" style="display:none; width:200px; height:30px;">
						The five minutes interval that the value applies. There are 12 intervals in an hour 
					</div>
					<div class="balloon" id="Hour" style="display:none; width:450px; height:35px;">
						The hour for which the value applies. Hour 1 represents the period from 0:00 to 1:00 (EST) i.e. midnight to one o’clock. Values range from 1 to 24
  	 				</div>
					<!-- create space for excel      &#xa0;   -->
					<div class="balloon" id="Schedules" style="display:none; width:150px; height:20px;">
						Hourly schedules &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;  &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; 
					</div>
					<div class="balloon" id="Date" style="display:none; width:300px; height:35px;">
						Is the trade day which is a period from midnight (EST) to the following midnight (EST)
					</div>
					<div class="balloon" id="CreationDate" style="display:none; width:150px; height:35px;">
						Report creation date and time in EST &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;                     
					</div>
					<div class="balloon" id="Net" style="display:none; width:180px; height:20px;">
						Net schedule (Export - Import)&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;
					</div>
					<div class="balloon" id="Import" style="display:none; width:180px; height:20px;">
						Scheduled imports of energy &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; 
					</div>
					<div class="balloon" id="Export" style="display:none; width:180px; height:20px;">
						Scheduled exports of energy   &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; 
					</div>
					<div class="balloon" id="Flow" style="display:none; width:150px; height:20px;">
						Flow of energy   &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0;  &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; &#xa0;&#xa0;&#xa0;&#xa0;&#xa0;&#xa0; 
					</div>
					<br/>
					<table width="100%">
						<tbody>
							<tr>
								<td align="left" width="25%" valign="top">
									<h1 align="left">
										<IMG alt="" src="https://reports-public.ieso.ca/images/logo.gif"/>
									</h1>
								</td>
								<td width="50%">
									<h1 align="center">
										<a class="isTip" onmouseover="makeItVisible('Title')" onmouseout="hideHelp('Title')" href="#">
											<xsl:value-of select="ieso:IMODocument/ieso:IMODocHeader/ieso:DocTitle"/>
										</a>
									</h1>
									<h2 align="center">
										<table align="center" class="subtable" cellspacing="5">
											<tr>
												<td align="right">
													<a class="isTip" onmouseover="makeItVisible('CreationDate')" onmouseout="hideHelp('CreationDate')" href="#">Created at </a>
												</td>
												<td align="left">
													<xsl:call-template name="Month">
														<xsl:with-param name="month">
															<xsl:value-of select="substring($createdAt, 6, 2)"/>
														</xsl:with-param>
													</xsl:call-template>
													<xsl:text> </xsl:text>
													<xsl:value-of select="substring($createdAt, 9, 2)"/>
													<xsl:text>, </xsl:text>
													<xsl:value-of select="substring($createdAt, 1, 4) "/>
													<xsl:text> </xsl:text>
													<xsl:value-of select="substring($createdAt, 12) "/>
													<xsl:text> </xsl:text>
												</td>
											</tr>
											<tr>
												<td align="right">
													<a class="isTip" onmouseover="makeItVisible('Date',event)" onmouseout="hideHelp('Date')" href="#">For </a>
												</td>
												<td align="left">
													<xsl:call-template name="Month">
														<xsl:with-param name="month">
															<xsl:value-of select="substring($deliveryDate, 6, 2)"/>
														</xsl:with-param>
													</xsl:call-template>
													<xsl:text> </xsl:text>
													<xsl:value-of select="substring($deliveryDate, 9, 2)"/>
													<xsl:text>, </xsl:text>
													<xsl:value-of select="substring($deliveryDate, 1, 4) "/>
													<xsl:text> </xsl:text>
													<xsl:value-of select="substring($deliveryDate, 12) "/>
												</td>
											</tr>
										</table>
									</h2>
								</td>
								<td width="25%" align="right" valign="top">
									<a href="https://reports-public.ieso.ca/docrefs/helpfile/IntertieScheduleFlow_h1.pdf">
										<b>
											<i>Help</i>
										</b>
									</a>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div class="report">
					<xsl:variable name="cnt">
						<xsl:value-of select="count(//ieso:IntertieZone)"/>
					</xsl:variable>
					<xsl:variable name="hourCnt">
						<xsl:value-of select="ieso:IMODocument/ieso:IMODocBody/ieso:IntertieZone[1]/ieso:Schedules/ieso:Schedule[last()]/ieso:Hour"/>
					</xsl:variable>
					<table border="1" bordercolor="#000000" cellspacing="0" cellpadding="0" bgcolor="white" align="center">
						<tbody>
							<tr>
								<td class="c1headc1" align="center">
									<a class="isTip" onmouseover="makeItVisible('Zone')" onmouseout="hideHelp('Zone')" href="#">										
											Zone
										</a>
								</td>
								<xsl:for-each select="ieso:IMODocument/ieso:IMODocBody/ieso:IntertieZone">
									<td class="c1colheadc1" align="center" colspan="3">
										<xsl:value-of select="ieso:IntertieZoneName"/>
									</td>
								</xsl:for-each>
								<td class="c1colheadc1" align="center" colspan="3">
												Total
									</td>
							</tr>
							<tr>
								<td class="c1headc1" align="center">
									<a class="isTip" onmouseover="makeItVisible('Hour')" onmouseout="hideHelp('Hour')" href="#">										
											Hour
										</a>
								</td>
								<xsl:call-template name="HeaderRow">
									<xsl:with-param name="classType">c1headc1</xsl:with-param>
									<xsl:with-param name="classType2">c1colheadc1</xsl:with-param>
									<xsl:with-param name="i">1</xsl:with-param>
									<xsl:with-param name="count">
										<xsl:value-of select="$cnt + 1"/>
									</xsl:with-param>
								</xsl:call-template>
							</tr>
							<xsl:call-template name="HourRow">
								<xsl:with-param name="node" select="ieso:IMODocument/ieso:IMODocBody"/>
								<xsl:with-param name="i">1</xsl:with-param>
								<xsl:with-param name="hourCount">
									<xsl:value-of select="$hourCnt"/>
								</xsl:with-param>
							</xsl:call-template>
						</tbody>
					</table>
				</div>
			</body>
		</html>
	</xsl:template>
	<xsl:template name="HeaderRow">
		<xsl:param name="classType"/>
		<xsl:param name="classType2"/>
		<xsl:param name="i"/>
		<xsl:param name="count"/>
		<xsl:if test="$i &lt;= $count">
			<td class="{$classType2}" align="center">
				<a class="isTip" onmouseover="makeItVisible('Import')" onmouseout="hideHelp('Import')" href="#">										
					Imp
				</a>
			</td>
			<td class="{$classType}" align="center">
				<a class="isTip" onmouseover="makeItVisible('Export')" onmouseout="hideHelp('Export')" href="#">										
					Exp
				</a>
			</td>
			<td class="{$classType}" align="center">
				<a class="isTip" onmouseover="makeItVisible('Flow')" onmouseout="hideHelp('Flow')" href="#">										
					Flow
				</a>
			</td>
		</xsl:if>
		<xsl:if test="$i &lt;= $count">
			<xsl:call-template name="HeaderRow">
				<xsl:with-param name="classType">
					<xsl:value-of select="$classType"/>
				</xsl:with-param>
				<xsl:with-param name="classType2">
					<xsl:value-of select="$classType2"/>
				</xsl:with-param>
				<xsl:with-param name="i">
					<xsl:value-of select="$i + 1"/>
				</xsl:with-param>
				<xsl:with-param name="count">
					<xsl:value-of select="$count"/>
				</xsl:with-param>
			</xsl:call-template>
		</xsl:if>
	</xsl:template>
	<xsl:template name="HourRow">
		<xsl:param name="node"/>
		<xsl:param name="i"/>
		<xsl:param name="hourCount"/>
		<xsl:if test="$i &lt;= $hourCount">
			<xsl:variable name="classType1">
				<xsl:choose>
					<xsl:when test="$i mod 2 = 1">c1datac1</xsl:when>
					<xsl:otherwise>c1datac2</xsl:otherwise>
				</xsl:choose>
			</xsl:variable>
			<xsl:variable name="classType2">
				<xsl:choose>
					<xsl:when test="$i mod 2 = 1">c2coldatac1</xsl:when>
					<xsl:otherwise>c2coldatac2</xsl:otherwise>
				</xsl:choose>
			</xsl:variable>
			<tr>
				<td class="{$classType1}" align="right">
					<xsl:value-of select="$i"/>
				</td>
				<xsl:for-each select="$node/ieso:IntertieZone">
					<xsl:call-template name="ZoneCells">
						<xsl:with-param name="node" select="current()"/>
						<xsl:with-param name="classType1">
							<xsl:value-of select="$classType1"/>
						</xsl:with-param>
						<xsl:with-param name="classType2">
							<xsl:value-of select="$classType2"/>
						</xsl:with-param>
						<xsl:with-param name="hour">
							<xsl:value-of select="$i"/>
						</xsl:with-param>
					</xsl:call-template>
				</xsl:for-each>
				<xsl:for-each select="$node/ieso:Totals">
					<xsl:call-template name="ZoneCells">
						<xsl:with-param name="node" select="current()"/>
						<xsl:with-param name="classType1">
							<xsl:value-of select="$classType1"/>
						</xsl:with-param>
						<xsl:with-param name="classType2">
							<xsl:value-of select="$classType2"/>
						</xsl:with-param>
						<xsl:with-param name="hour">
							<xsl:value-of select="$i"/>
						</xsl:with-param>
					</xsl:call-template>
				</xsl:for-each>
			</tr>
		</xsl:if>
		<xsl:if test="$i &lt;= $hourCount">
			<xsl:call-template name="HourRow">
				<xsl:with-param name="node" select="$node"/>
				<xsl:with-param name="i">
					<xsl:value-of select="$i + 1"/>
				</xsl:with-param>
				<xsl:with-param name="hourCount">
					<xsl:value-of select="$hourCount"/>
				</xsl:with-param>
			</xsl:call-template>
		</xsl:if>
	</xsl:template>
	<xsl:template name="ZoneCells">
		<xsl:param name="node"/>
		<xsl:param name="classType1"/>
		<xsl:param name="classType2"/>
		<xsl:param name="hour"/>
		<!-- check xml file has this hour if not put blank-->
		<xsl:choose>
			<xsl:when test="$hour  = $node/ieso:Schedules/ieso:Schedule/ieso:Hour[$hour]">
				<td class="{$classType2}" align="right">
					<xsl:value-of select="$node/ieso:Schedules/ieso:Schedule[ieso:Hour = $hour]/ieso:Import"/>
				</td>
				<td class="{$classType1}" align="right">
					<xsl:value-of select="$node/ieso:Schedules/ieso:Schedule[ieso:Hour = $hour]/ieso:Export"/>
				</td>
			</xsl:when>
			<xsl:otherwise>
				<td class="{$classType2}">
				</td>
				<td class="{$classType1}">
				</td>
			</xsl:otherwise>
		</xsl:choose>
		<xsl:choose>
			<xsl:when test="$hour  = $node/ieso:Actuals/ieso:Actual/ieso:Hour[$hour]">
				<td class="{$classType1}" align="right">
					<!-- generate pop-up-->
					<div class="flowBalloon" id="{generate-id($node/ieso:Actuals/ieso:Actual[ieso:Hour = $hour])}" style="display:none; width:130px; height:305px;">
						<table border="1" bordercolor="#000000" cellpadding="0" align="center">
							<tr>
								<td class="c1headc1" colspan="2" align="center" width="130">
									<xsl:variable name="zoneNam">
										<xsl:choose>
											<xsl:when test="$node/ieso:IntertieZoneName != ''">
												<xsl:value-of select="$node/ieso:IntertieZoneName"/>
											</xsl:when>
											<xsl:otherwise>
												<xsl:text>Total</xsl:text>
											</xsl:otherwise>
										</xsl:choose>
									</xsl:variable>
									Flows for <xsl:value-of select="$zoneNam"/>
									<br/> Hour <xsl:value-of select="$hour"/>
								</td>
							</tr>
							<tr>
								<td class="c1headc1" align="center" width="65">
									Interval
								</td>
								<td class="c1headc1" align="center" width="65">
									Flow
								</td>
							</tr>
							<xsl:call-template name="IntervalFlow">
								<xsl:with-param name="node" select="$node/ieso:Actuals/ieso:Actual[ieso:Hour = $hour]"/>
								<xsl:with-param name="i">1</xsl:with-param>
								<xsl:with-param name="count">12</xsl:with-param>
							</xsl:call-template>
						</table>
					</div>
					<a class="isTip" onmouseover="makeItVisible('{generate-id($node/ieso:Actuals/ieso:Actual[ieso:Hour = $hour])}')" onmouseout="hideHelp('{generate-id($node/ieso:Actuals/ieso:Actual[ieso:Hour = $hour])}')" href="#">
						<!-- This template will calculate total value of Flow for all intervals(1-12) -->
						<xsl:call-template name="AVGFlow">
							<xsl:with-param name="node" select="$node/ieso:Actuals/ieso:Actual[ieso:Hour = $hour]"/>
							<xsl:with-param name="total">0</xsl:with-param>
							<xsl:with-param name="i">1</xsl:with-param>
							<xsl:with-param name="count">12</xsl:with-param>
						</xsl:call-template>
					</a>
				</td>
			</xsl:when>
			<xsl:otherwise>
				<td class="{$classType1}">
				</td>
			</xsl:otherwise>
		</xsl:choose>
	</xsl:template>
	<xsl:template name="IntervalFlow">
		<xsl:param name="node"/>
		<xsl:param name="i"/>
		<xsl:param name="count"/>
		<xsl:if test="$i &lt;= $count">
			<xsl:variable name="classType">
				<xsl:choose>
					<xsl:when test="$i mod 2 = 1">c1datac1</xsl:when>
					<xsl:otherwise>c1datac2</xsl:otherwise>
				</xsl:choose>
			</xsl:variable>
			<tr>
				<td class="{$classType}" align="center" width="65">
					<xsl:value-of select="$i"/>
				</td>
				<td class="{$classType}" align="center" width="65">
					<xsl:value-of select="round($node[ieso:Interval = $i]/ieso:Flow)"/>
				</td>
			</tr>
		</xsl:if>
		<xsl:if test="$i &lt;= $count">
			<xsl:call-template name="IntervalFlow">
				<xsl:with-param name="node" select="$node"/>
				<xsl:with-param name="i">
					<xsl:value-of select="$i + 1"/>
				</xsl:with-param>
				<xsl:with-param name="count">
					<xsl:value-of select="$count"/>
				</xsl:with-param>
			</xsl:call-template>
		</xsl:if>
	</xsl:template>
	<xsl:template name="AVGFlow">
		<xsl:param name="node"/>
		<xsl:param name="total"/>
		<xsl:param name="i"/>
		<xsl:param name="count"/>
		<xsl:if test="$i &gt; $count">
			<xsl:if test="$total &gt;= 0">
				<xsl:value-of select="round($total div 12)"/>
			</xsl:if>
			<!-- abs() function is not available in xpath. to acheive this I use substring-->
			<xsl:if test="$total &lt; 0">
				-<xsl:value-of select="round(substring-after($total,'-') div 12)"/>
			</xsl:if>
		</xsl:if>
		<xsl:if test="$i &lt;= $count">
			<xsl:call-template name="AVGFlow">
				<xsl:with-param name="node" select="$node"/>
				<xsl:with-param name="total">
					<xsl:value-of select="$total + round($node[ieso:Interval = $i]/ieso:Flow)"/>
				</xsl:with-param>
				<xsl:with-param name="i">
					<xsl:value-of select="$i + 1"/>
				</xsl:with-param>
				<xsl:with-param name="count">
					<xsl:value-of select="$count"/>
				</xsl:with-param>
			</xsl:call-template>
		</xsl:if>
	</xsl:template>
	<xsl:template name="Month">
		<xsl:param name="month"/>
		<xsl:choose>
			<xsl:when test="$month='01'">
				<xsl:text>Jan</xsl:text>
			</xsl:when>
			<xsl:when test="$month='02'">
				<xsl:text>Feb</xsl:text>
			</xsl:when>
			<xsl:when test="$month='03'">
				<xsl:text>Mar</xsl:text>
			</xsl:when>
			<xsl:when test="$month='04'">
				<xsl:text>Apr</xsl:text>
			</xsl:when>
			<xsl:when test="$month='05'">
				<xsl:text>May</xsl:text>
			</xsl:when>
			<xsl:when test="$month='06'">
				<xsl:text>Jun</xsl:text>
			</xsl:when>
			<xsl:when test="$month='07'">
				<xsl:text>Jul</xsl:text>
			</xsl:when>
			<xsl:when test="$month='08'">
				<xsl:text>Aug</xsl:text>
			</xsl:when>
			<xsl:when test="$month='09'">
				<xsl:text>Sep</xsl:text>
			</xsl:when>
			<xsl:when test="$month='10'">
				<xsl:text>Oct</xsl:text>
			</xsl:when>
			<xsl:when test="$month='11'">
				<xsl:text>Nov</xsl:text>
			</xsl:when>
			<xsl:when test="$month='12'">
				<xsl:text>Dec</xsl:text>
			</xsl:when>
		</xsl:choose>
	</xsl:template>
	<xsl:template name="Time">
		<xsl:param name="hour"/>
		<xsl:choose>
			<xsl:when test="$hour &lt; '13'">
				<xsl:text>a.m.</xsl:text>
			</xsl:when>
			<xsl:when test="$hour &gt; '12'">
				<xsl:text>p.m.</xsl:text>
			</xsl:when>
		</xsl:choose>
	</xsl:template>
</xsl:stylesheet>
