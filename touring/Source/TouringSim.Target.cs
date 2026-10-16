using UnrealBuildTool;

public class TouringSimTarget : TargetRules
{
	public TouringSimTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("FukuokaDrive");
	}
}
