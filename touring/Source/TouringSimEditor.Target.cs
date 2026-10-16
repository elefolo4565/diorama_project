using UnrealBuildTool;

public class TouringSimEditorTarget : TargetRules
{
	public TouringSimEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("FukuokaDrive");
	}
}
