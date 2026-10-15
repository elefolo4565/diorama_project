using UnrealBuildTool;

public class SikanosimaEditorTarget : TargetRules
{
	public SikanosimaEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("FukuokaDrive");
	}
}
