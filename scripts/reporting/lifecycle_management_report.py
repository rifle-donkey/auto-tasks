from automation_core.base_task import BaseTask
from automation_core.auth import get_credential
from automation_core.utils import set_timestamp
from automation_core.networking import make_api_request
from automation_core.reporting import write_list_to_csv, write_to_json, send_to_splunk
import os
import csv
import json
from datetime import datetime, timedelta


class LifecycleManagementReport(BaseTask):
    name = "lifecycle_management_report"
    description = "Generate device lifecycle and End-of-Life (EoL/EoS) reports from IPAM database"
    category = "reporting"
    dependencies = ["IPAM"]
    default_schedule = "0 10 * * 1"  # Weekly on Monday at 10 AM
    max_runtime = 1200
    
    def __init__(self):
        super().__init__()
        self.output_dir = "/var/automation_file/reporting"
        
    def execute(self):
        try:
            self.log("Starting lifecycle management report generation")
            
            # Get lifecycle data from IPAM
            lifecycle_data = self._get_lifecycle_data()
            if not lifecycle_data:
                self.log("No lifecycle data found", level="WARNING")
                return {"status": "skipped", "reason": "no_data"}
            
            # Analyze lifecycle status
            eol_analysis = self._analyze_eol_status(lifecycle_data)
            eos_analysis = self._analyze_eos_status(lifecycle_data)
            risk_assessment = self._assess_lifecycle_risks(lifecycle_data)
            
            # Generate reports
            report_files = []
            
            # EoL devices CSV report
            eol_csv = self._generate_eol_csv_report(eol_analysis)
            if eol_csv:
                report_files.append(eol_csv)
            
            # EoS devices CSV report
            eos_csv = self._generate_eos_csv_report(eos_analysis)
            if eos_csv:
                report_files.append(eos_csv)
            
            # Risk assessment JSON report
            risk_json = self._generate_risk_assessment_report(risk_assessment)
            if risk_json:
                report_files.append(risk_json)
            
            # Send alerts for critical devices
            self._send_lifecycle_alerts(eol_analysis, eos_analysis)
            
            self.log(f"Lifecycle report generation complete. Analyzed {len(lifecycle_data)} devices")
            
            return {
                "status": "success",
                "devices_analyzed": len(lifecycle_data),
                "eol_devices": len(eol_analysis.get('current_eol', [])),
                "eos_devices": len(eos_analysis.get('current_eos', [])),
                "critical_devices": len(risk_assessment.get('critical_risk', [])),
                "reports_generated": len(report_files),
                "report_files": report_files,
                "timestamp": set_timestamp()
            }
            
        except Exception as e:
            self.log(f"Lifecycle management report failed: {e}", level="ERROR")
            return {"status": "error", "error": str(e)}
    
    def _get_lifecycle_data(self):
        """Get device lifecycle data from IPAM"""
        try:
            ipam_user, ipam_pass = get_credential("IPAM")
            
            # Get devices with lifecycle information
            response = make_api_request(
                method="GET",
                url=f"{os.getenv('IPAM_BASE_URL')}/api/devices/lifecycle/",
                auth=(ipam_user, ipam_pass),
                timeout=30
            )
            
            if response and response.get("status_code") == 200:
                devices = response.get("data", [])
                
                # Process and enrich lifecycle data
                processed_devices = []
                for device in devices:
                    processed_device = self._process_lifecycle_data(device)
                    if processed_device:
                        processed_devices.append(processed_device)
                
                self.log(f"Retrieved lifecycle data for {len(processed_devices)} devices")
                return processed_devices
            
            return []
            
        except Exception as e:
            self.log(f"Error getting lifecycle data: {e}", level="ERROR")
            return []
    
    def _process_lifecycle_data(self, device):
        """Process and enrich device lifecycle data"""
        try:
            processed = {
                'hostname': device.get('hostname'),
                'ip_address': device.get('ip_address'),
                'vendor': device.get('vendor'),
                'model': device.get('model'),
                'serial_number': device.get('serial_number'),
                'software_version': device.get('software_version'),
                'site': device.get('site'),
                'device_type': device.get('device_type'),
                'purchase_date': device.get('purchase_date'),
                'warranty_end_date': device.get('warranty_end_date'),
                'eol_date': device.get('end_of_life_date'),
                'eos_date': device.get('end_of_support_date'),
                'eol_status': self._determine_eol_status(device),
                'eos_status': self._determine_eos_status(device),
                'lifecycle_stage': self._determine_lifecycle_stage(device),
                'risk_level': self._calculate_risk_level(device),
                'replacement_priority': device.get('replacement_priority', 'Medium'),
                'business_criticality': device.get('business_criticality', 'Medium'),
                'last_updated': device.get('last_updated'),
                'report_timestamp': set_timestamp()
            }
            
            return processed
            
        except Exception as e:
            self.log(f"Error processing lifecycle data: {e}", level="ERROR")
            return None
    
    def _determine_eol_status(self, device):
        """Determine End-of-Life status"""
        try:
            eol_date_str = device.get('end_of_life_date')
            if not eol_date_str:
                return 'Unknown'
            
            eol_date = datetime.strptime(eol_date_str, '%Y-%m-%d')
            today = datetime.now()
            days_to_eol = (eol_date - today).days
            
            if days_to_eol < 0:
                return 'End-of-Life'
            elif days_to_eol < 180:  # 6 months
                return 'Critical'
            elif days_to_eol < 365:  # 1 year
                return 'Warning'
            else:
                return 'Active'
                
        except Exception:
            return 'Unknown'
    
    def _determine_eos_status(self, device):
        """Determine End-of-Support status"""
        try:
            eos_date_str = device.get('end_of_support_date')
            if not eos_date_str:
                return 'Unknown'
            
            eos_date = datetime.strptime(eos_date_str, '%Y-%m-%d')
            today = datetime.now()
            days_to_eos = (eos_date - today).days
            
            if days_to_eos < 0:
                return 'End-of-Support'
            elif days_to_eos < 180:  # 6 months
                return 'Critical'
            elif days_to_eos < 365:  # 1 year
                return 'Warning'
            else:
                return 'Supported'
                
        except Exception:
            return 'Unknown'
    
    def _determine_lifecycle_stage(self, device):
        """Determine overall lifecycle stage"""
        eol_status = self._determine_eol_status(device)
        eos_status = self._determine_eos_status(device)
        
        if eol_status == 'End-of-Life' or eos_status == 'End-of-Support':
            return 'End-of-Life'
        elif eol_status == 'Critical' or eos_status == 'Critical':
            return 'Critical'
        elif eol_status == 'Warning' or eos_status == 'Warning':
            return 'Warning'
        else:
            return 'Active'
    
    def _calculate_risk_level(self, device):
        """Calculate overall risk level for device"""
        try:
            eol_status = self._determine_eol_status(device)
            eos_status = self._determine_eos_status(device)
            criticality = device.get('business_criticality', 'Medium')
            
            risk_score = 0
            
            # EoL/EoS status scoring
            if eol_status == 'End-of-Life' or eos_status == 'End-of-Support':
                risk_score += 4
            elif eol_status == 'Critical' or eos_status == 'Critical':
                risk_score += 3
            elif eol_status == 'Warning' or eos_status == 'Warning':
                risk_score += 2
            else:
                risk_score += 1
            
            # Business criticality multiplier
            if criticality == 'High':
                risk_score *= 1.5
            elif criticality == 'Critical':
                risk_score *= 2.0
            
            # Determine risk level
            if risk_score >= 6:
                return 'Critical'
            elif risk_score >= 4:
                return 'High'
            elif risk_score >= 2:
                return 'Medium'
            else:
                return 'Low'
                
        except Exception:
            return 'Medium'
    
    def _analyze_eol_status(self, lifecycle_data):
        """Analyze End-of-Life status across all devices"""
        try:
            analysis = {
                'current_eol': [],
                'critical_eol': [],
                'warning_eol': [],
                'active': []
            }
            
            for device in lifecycle_data:
                eol_status = device.get('eol_status')
                
                if eol_status == 'End-of-Life':
                    analysis['current_eol'].append(device)
                elif eol_status == 'Critical':
                    analysis['critical_eol'].append(device)
                elif eol_status == 'Warning':
                    analysis['warning_eol'].append(device)
                else:
                    analysis['active'].append(device)
            
            return analysis
            
        except Exception as e:
            self.log(f"Error analyzing EoL status: {e}", level="ERROR")
            return {}
    
    def _analyze_eos_status(self, lifecycle_data):
        """Analyze End-of-Support status across all devices"""
        try:
            analysis = {
                'current_eos': [],
                'critical_eos': [],
                'warning_eos': [],
                'supported': []
            }
            
            for device in lifecycle_data:
                eos_status = device.get('eos_status')
                
                if eos_status == 'End-of-Support':
                    analysis['current_eos'].append(device)
                elif eos_status == 'Critical':
                    analysis['critical_eos'].append(device)
                elif eos_status == 'Warning':
                    analysis['warning_eos'].append(device)
                else:
                    analysis['supported'].append(device)
            
            return analysis
            
        except Exception as e:
            self.log(f"Error analyzing EoS status: {e}", level="ERROR")
            return {}
    
    def _assess_lifecycle_risks(self, lifecycle_data):
        """Assess overall lifecycle risks"""
        try:
            risk_assessment = {
                'critical_risk': [],
                'high_risk': [],
                'medium_risk': [],
                'low_risk': []
            }
            
            for device in lifecycle_data:
                risk_level = device.get('risk_level')
                
                if risk_level == 'Critical':
                    risk_assessment['critical_risk'].append(device)
                elif risk_level == 'High':
                    risk_assessment['high_risk'].append(device)
                elif risk_level == 'Medium':
                    risk_assessment['medium_risk'].append(device)
                else:
                    risk_assessment['low_risk'].append(device)
            
            return risk_assessment
            
        except Exception as e:
            self.log(f"Error assessing lifecycle risks: {e}", level="ERROR")
            return {}
    
    def _generate_eol_csv_report(self, eol_analysis):
        """Generate CSV report for End-of-Life devices"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_file = f"{self.output_dir}/eol_devices_{timestamp}.csv"
            
            # Combine all EoL categories
            all_eol_devices = (
                eol_analysis.get('current_eol', []) +
                eol_analysis.get('critical_eol', []) +
                eol_analysis.get('warning_eol', [])
            )
            
            if all_eol_devices:
                write_list_to_csv(all_eol_devices, csv_file)
                self.log(f"EoL devices CSV report generated: {csv_file}")
                return csv_file
            
            return None
            
        except Exception as e:
            self.log(f"Error generating EoL CSV report: {e}", level="ERROR")
            return None
    
    def _generate_eos_csv_report(self, eos_analysis):
        """Generate CSV report for End-of-Support devices"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_file = f"{self.output_dir}/eos_devices_{timestamp}.csv"
            
            # Combine all EoS categories
            all_eos_devices = (
                eos_analysis.get('current_eos', []) +
                eos_analysis.get('critical_eos', []) +
                eos_analysis.get('warning_eos', [])
            )
            
            if all_eos_devices:
                write_list_to_csv(all_eos_devices, csv_file)
                self.log(f"EoS devices CSV report generated: {csv_file}")
                return csv_file
            
            return None
            
        except Exception as e:
            self.log(f"Error generating EoS CSV report: {e}", level="ERROR")
            return None
    
    def _generate_risk_assessment_report(self, risk_assessment):
        """Generate JSON risk assessment report"""
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_file = f"{self.output_dir}/lifecycle_risk_assessment_{timestamp}.json"
            
            report_data = {
                "report_metadata": {
                    "generation_timestamp": set_timestamp(),
                    "report_type": "lifecycle_risk_assessment"
                },
                "risk_assessment": risk_assessment
            }
            
            write_to_json(report_data, json_file)
            self.log(f"Risk assessment report generated: {json_file}")
            return json_file
            
        except Exception as e:
            self.log(f"Error generating risk assessment report: {e}", level="ERROR")
            return None
    
    def _send_lifecycle_alerts(self, eol_analysis, eos_analysis):
        """Send alerts for critical lifecycle status"""
        try:
            critical_devices = (
                eol_analysis.get('current_eol', []) +
                eol_analysis.get('critical_eol', []) +
                eos_analysis.get('current_eos', []) +
                eos_analysis.get('critical_eos', [])
            )
            
            if critical_devices:
                alert_data = {
                    "timestamp": set_timestamp(),
                    "event_type": "lifecycle_alert",
                    "critical_device_count": len(critical_devices),
                    "devices": [
                        {
                            "hostname": device.get('hostname'),
                            "site": device.get('site'),
                            "lifecycle_stage": device.get('lifecycle_stage'),
                            "risk_level": device.get('risk_level')
                        }
                        for device in critical_devices
                    ]
                }
                
                # Send to Splunk
                send_to_splunk(alert_data, source="lifecycle_alerts")
                
                self.log(f"Lifecycle alerts sent for {len(critical_devices)} critical devices")
            
        except Exception as e:
            self.log(f"Error sending lifecycle alerts: {e}", level="ERROR")


# Task registration for auto-discovery
task_class = LifecycleManagementReport