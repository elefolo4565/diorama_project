using UnrealBuildTool;

public class SikanosimaTarget : TargetRules
{
	public SikanosimaTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("FukuokaDrive");
	}
}
