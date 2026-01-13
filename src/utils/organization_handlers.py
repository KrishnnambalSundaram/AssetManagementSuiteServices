import asyncio
import logging
import os
import subprocess
import sys
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class OrganizationHandlers:
    """Utility class to handle organization-related events and triggers"""
    
    @staticmethod
    async def run_paginated_job_logs_for_organization(organization_id: str) -> bool:
        """
        Run the paginated job logs script for a newly created organization
        
        Args:
            organization_id: The ID of the organization to process
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Starting paginated job logs for organization {organization_id}")
            
            # Get the script path
            script_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "scripts", 
                "paginated_job_logs.py"
            )
            
            # Prepare the command
            cmd = [
                sys.executable,
                script_path,
                "--organization_id", str(organization_id),
                "--page_size", "1000",
                "--max_pages", "100"
            ]
            
            logger.info(f"Executing command: {' '.join(cmd)}")
            
            # Run the script asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            
            # Wait for completion with timeout (30 minutes)
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=1800  # 30 minutes timeout
                )
                
                if process.returncode == 0:
                    logger.info(f"Successfully completed paginated job logs for organization {organization_id}")
                    logger.debug(f"Script output: {stdout.decode()}")
                    return True
                else:
                    logger.error(f"Paginated job logs failed for organization {organization_id}")
                    logger.error(f"Error output: {stderr.decode()}")
                    return False
                    
            except asyncio.TimeoutError:
                logger.error(f"Paginated job logs timed out for organization {organization_id}")
                process.kill()
                return False
                
        except Exception as e:
            logger.error(f"Error running paginated job logs for organization {organization_id}: {e}")
            return False
    
    @staticmethod
    def run_paginated_job_logs_sync(organization_id: str) -> bool:
        """
        Synchronous version of run_paginated_job_logs_for_organization
        This can be used in non-async contexts
        
        Args:
            organization_id: The ID of the organization to process
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Starting paginated job logs (sync) for organization {organization_id}")
            
            # Get the script path
            script_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "scripts", 
                "paginated_job_logs.py"
            )
            
            # Prepare the command
            cmd = [
                sys.executable,
                script_path,
                "--organization_id", str(organization_id),
                "--page_size", "1000",
                "--max_pages", "100"
            ]
            
            logger.info(f"Executing command: {' '.join(cmd)}")
            
            # Run the script synchronously
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes timeout
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully completed paginated job logs for organization {organization_id}")
                logger.debug(f"Script output: {result.stdout}")
                return True
            else:
                logger.error(f"Paginated job logs failed for organization {organization_id}")
                logger.error(f"Error output: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Paginated job logs timed out for organization {organization_id}")
            return False
        except Exception as e:
            logger.error(f"Error running paginated job logs for organization {organization_id}: {e}")
            return False
