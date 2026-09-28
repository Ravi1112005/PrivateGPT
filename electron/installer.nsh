!macro customInstall
  DetailPrint "Setting up Python environment and dependencies..."
  nsExec::ExecToLog '"$INSTDIR\resources\setup_env.bat" "$INSTDIR\resources"'
!macroend

!macro customUnInstall
  DetailPrint "Removing environments..."
  RMDir /r "$INSTDIR\resources\venv"
!macroend
