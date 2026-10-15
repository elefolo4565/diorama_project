using UnrealBuildTool;

public class FukuokaDrive : ModuleRules
{
	public FukuokaDrive(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "Slate", "SlateCore", "AudioMixer", "Landscape", "Water", "AssetRegistry"
		});
	}
}
