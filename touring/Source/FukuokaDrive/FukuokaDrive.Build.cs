using UnrealBuildTool;

public class FukuokaDrive : ModuleRules
{
	public FukuokaDrive(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		// 各 .cpp は無名名前空間に同じ名前の定数 (DebugMessageKey など) を持つので、まとめてコンパイルしない
		bUseUnity = false;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "Slate", "SlateCore", "AudioMixer", "Landscape", "Water", "AssetRegistry", "Projects"
		});
	}
}
